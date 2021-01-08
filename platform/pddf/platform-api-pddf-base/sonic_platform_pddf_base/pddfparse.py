#!/usr/bin/env python
import glob
import json
from jsonschema import validate
import os
import re
import subprocess
import time
import unicodedata

bmc_cache = {}
cache = {}
SONIC_CFGGEN_PATH = '/usr/local/bin/sonic-cfggen'
HWSKU_KEY = 'DEVICE_METADATA.localhost.hwsku'
PLATFORM_KEY = 'DEVICE_METADATA.localhost.platform'

dirname = os.path.dirname(os.path.realpath(__file__))

color_map = {
    "STATUS_LED_COLOR_GREEN": "green",
    "STATUS_LED_COLOR_RED": "red",
    "STATUS_LED_COLOR_AMBER": "amber",
    "STATUS_LED_COLOR_BLUE": "blue",
    "STATUS_LED_COLOR_GREEN_BLINK": "blinking green",
    "STATUS_LED_COLOR_RED_BLINK": "blinking red",
    "STATUS_LED_COLOR_AMBER_BLINK": "blinking amber",
    "STATUS_LED_COLOR_BLUE_BLINK": "blinking blue",
    "STATUS_LED_COLOR_OFF": "off"
}


class PddfParse():
    def __init__(self):
        if not os.path.exists("/usr/share/sonic/platform"):
            self.platform, self.hwsku = self.get_platform_and_hwsku()
            os.symlink("/usr/share/sonic/device/"+self.platform, "/usr/share/sonic/platform")

        try:
            with open('/usr/share/sonic/platform/pddf/pddf-device.json') as f:
                self.data = json.load(f)
        except IOError:
            if os.path.exists('/usr/share/sonic/platform'):
                os.unlink("/usr/share/sonic/platform")

        self.data_sysfs_obj = {}
        self.sysfs_obj = {}

    # Returns platform and HW SKU

    def get_platform_and_hwsku(self):
        try:
            proc = subprocess.Popen([SONIC_CFGGEN_PATH, '-H', '-v', PLATFORM_KEY],
                                    stdout=subprocess.PIPE,
                                    shell=False,
                                    stderr=subprocess.STDOUT)
            stdout = proc.communicate()[0]
            proc.wait()
            platform = stdout.rstrip('\n')

            proc = subprocess.Popen([SONIC_CFGGEN_PATH, '-d', '-v', HWSKU_KEY],
                                    stdout=subprocess.PIPE,
                                    shell=False,
                                    stderr=subprocess.STDOUT)
            stdout = proc.communicate()[0]
            proc.wait()
            hwsku = stdout.rstrip('\n')
        except OSError as e:
            raise OSError("Cannot detect platform")

        return (platform, hwsku)

    #################################################################################################################
    #   GENERIC DEFS
    #################################################################################################################
    def runcmd(self, cmd):
        rc = os.system(cmd)
        if rc != 0:
            print("%s -- command failed" % cmd)
        return rc

    def get_dev_idx(self, dev, ops):
        parent = dev['dev_info']['virt_parent']
        pdev = self.data[parent]

        return pdev['dev_attr']['dev_idx']

    def get_path(self, target, attr):
        aa = target + attr

        if aa in cache:
            return cache[aa]

        string = None
        p = re.search(r'\d+$', target)
        if p is None:
            for bb in filter(re.compile(target).search, self.data.keys()):
                path = self.dev_parse(self.data[bb], {"cmd": "show_attr", "target": bb, "attr": attr})
                if path != "":
                    string = path
        else:
            if target in self.data.keys():
                path = self.dev_parse(self.data[target], {"cmd": "show_attr", "target": target, "attr": attr})
                if path != "":
                    string = path

        if string is not None:
            string = string.rstrip()

        cache[aa] = string
        return string

    def get_device_type(self, key):
        if key not in self.data.keys():
            return None
        return self.data[key]['dev_info']['device_type']

    def get_platform(self):
        return self.data['PLATFORM']

    def get_num_psu_fans(self, dev):
        if dev not in self.data.keys():
            return 0

        if 'num_psu_fans' not in self.data[dev]['dev_attr']:
            return 0

        return self.data[dev]['dev_attr']['num_psu_fans']

    def get_led_path(self):
        return ("pddf/devices/led")

    def get_led_cur_state_path(self):
        return ("pddf/devices/led/cur_state")

    def get_led_color(self):
        color_f = "/sys/kernel/pddf/devices/led/cur_state/color"
        try:
            with open(color_f, 'r') as f:
                color = f.read().strip("\r\n")
        except IOError:
            return ("Error")

        return (color_map[color])

    def get_led_color_devtype(self, key):
        attr_list = self.data[key]['i2c']['attr_list']
        for attr in attr_list:
            if 'attr_devtype' in attr:
                return attr['attr_devtype'].strip()
            else:
                return 'cpld'

    def get_led_color_from_gpio(self, led_device_name):
        attr_list = self.data[led_device_name]['i2c']['attr_list']
        attr = attr_list[0]
        if ':' in attr['bits']:
            bits_list = attr['bits'].split(':')
            bits_list.sort(reverse=True)
            max_bit = int(bits_list[0])
        else:
            max_bit = 0
        base_offset = int(attr['swpld_addr_offset'], 16)
        value = 0
        bit = 0
        while bit <= max_bit:
            offset = base_offset + bit
            if 'attr_devname' in attr:
                attr_path = self.get_gpio_attr_path(self.data[attr['attr_devname']], hex(offset))
            else:
                status = "[FAILED] attr_devname is not configured"
                return (status)
            if not os.path.exists(attr_path):
                status = "[FAILED] {} does not exist".format(attr_path)
                return (status)
            cmd = 'cat ' + attr_path
            gpio_value = subprocess.check_output(cmd, shell=True)
            value |= int(gpio_value) << bit
            bit += 1

        for attr in attr_list:
            if int(attr['value'].strip(), 16) == value:
                return(color_map[attr['attr_name']])
        return (color_map['STATUS_LED_COLOR_OFF'])

    def get_led_color_from_cpld(self, led_device_name):
        index = self.data[led_device_name]['dev_attr']['index']
        device_name = self.data[led_device_name]['dev_info']['device_name']
        self.create_attr('device_name', device_name,  self.get_led_path())
        self.create_attr('index', index, self.get_led_path())
        self.create_attr('dev_ops', 'get_status',  self.get_led_path())
        return self.get_led_color()

    def set_led_color_from_gpio(self, led_device_name, color):
        attr_list = self.data[led_device_name]['i2c']['attr_list']
        for attr in attr_list:
            if attr['attr_name'].strip() == color.strip():
                base_offset = int(attr['swpld_addr_offset'], 16)
                if ':' in attr['bits']:
                    bits_list = attr['bits'].split(':')
                    bits_list.sort(reverse=True)
                    max_bit = int(bits_list[0])
                else:
                    max_bit = 0
                value = int(attr['value'], 16)
                i = 0
                while i <= max_bit:
                    _value = (value >> i) & 1
                    base_offset += i
                    attr_path = self.get_gpio_attr_path(self.data[attr['attr_devname']], hex(base_offset))
                    i += 1
                    try:
                        cmd = "echo {} > {}".format(_value, attr_path)
                        self.runcmd(cmd)
                    except Exception as e:
                        print("Invalid gpio path : " + attr_path)
                        return (False)
        return (True)

    def set_led_color_from_cpld(self, led_device_name, color):
        index = self.data[led_device_name]['dev_attr']['index']
        device_name = self.data[led_device_name]['dev_info']['device_name']
        self.create_attr('device_name', device_name,  self.get_led_path())
        self.create_attr('index', index, self.get_led_path())
        self.create_attr('color', color, self.get_led_cur_state_path())
        self.create_attr('dev_ops', 'set_status',  self.get_led_path())
        return (True)

    def get_system_led_color(self, led_device_name):
        if led_device_name not in self.data.keys():
            status = "[FAILED] " + led_device_name + " is not configured"
            return (status)

        type = self.get_led_color_devtype(led_device_name)

        if type == 'gpio':
            color = self.get_led_color_from_gpio(led_device_name)
        elif type == 'cpld':
            color = self.get_led_color_from_cpld(led_device_name)
        return color

    def set_system_led_color(self, led_device_name, color):
        result, msg = self.is_supported_sysled_state(led_device_name, color)
        if result == False:
            print(msg)
            return (result)

        type = self.get_led_color_devtype(led_device_name)

        if type == 'gpio':
            return (self.set_led_color_from_gpio(led_device_name, color))
        else:
            return (self.set_led_color_from_cpld(led_device_name, color))

    ###################################################################################################################
    #   SHOW ATTRIBIUTES DEFS
    ###################################################################################################################
    def is_led_device_configured(self, device_name, attr_name):
        if device_name in self.data.keys():
            attr_list = self.data[device_name]['i2c']['attr_list']
            for attr in attr_list:
                if attr['attr_name'].strip() == attr_name.strip():
                    return (True)
        return (False)

    def show_device_sysfs(self, dev, ops):
        parent = dev['dev_info']['device_parent']
        pdev = self.data[parent]
        if pdev['dev_info']['device_parent'] == 'SYSTEM':
            return "/sys/bus/i2c/devices/"+"i2c-%d" % int(pdev['i2c']['topo_info']['dev_addr'], 0)
        return self.show_device_sysfs(pdev, ops) + "/" + "i2c-%d" % int(dev['i2c']['topo_info']['parent_bus'], 0)

    # This is alid for 'at24' type of EEPROM devices. Only one attribtue 'eeprom'

    def show_attr_eeprom_device(self, dev, ops):
        str = ""
        attr_name = ops['attr']
        attr_list = dev['i2c']['attr_list']
        KEY = "eeprom"
        dsysfs_path = ""

        if KEY not in self.data_sysfs_obj:
            self.data_sysfs_obj[KEY] = []

        for attr in attr_list:
            if attr_name == attr['attr_name'] or attr_name == 'all':
                if 'drv_attr_name' in attr.keys():
                    real_name = attr['drv_attr_name']
                else:
                    real_name = attr['attr_name']

                dsysfs_path = self.show_device_sysfs(dev, ops) + \
                    "/%d-00%x" % (int(dev['i2c']['topo_info']['parent_bus'], 0),
                                  int(dev['i2c']['topo_info']['dev_addr'], 0)) + \
                    "/%s" % real_name
                if dsysfs_path not in self.data_sysfs_obj[KEY]:
                    self.data_sysfs_obj[KEY].append(dsysfs_path)
                str += dsysfs_path+"\n"
        return str

    def show_attr_gpio_device(self, dev, ops):
        ret = ""
        KEY = "gpio"
        if KEY not in self.data_sysfs_obj:
            self.data_sysfs_obj[KEY] = []

        return ret

    def show_attr_mux_device(self, dev, ops):
        ret = ""
        KEY = "mux"
        if KEY not in self.data_sysfs_obj:
            self.data_sysfs_obj[KEY] = []

        return ret

    def get_gpio_attr_path(self, dev, offset):
        base = int(dev['i2c']['dev_attr']['gpio_base'], 16)
        port_num = base + int(offset, 16)
        gpio_name = 'gpio'+str(port_num)
        path = '/sys/class/gpio/'+gpio_name+'/value'
        return path

    def show_attr_psu_i2c_device(self, dev, ops):
        target = ops['target']
        attr_name = ops['attr']
        ret = ""
        KEY = "psu"
        dsysfs_path = ""

        if KEY not in self.data_sysfs_obj:
            self.data_sysfs_obj[KEY] = []

        if target == 'all' or target == dev['dev_info']['virt_parent']:
            attr_list = dev['i2c']['attr_list']
            for attr in attr_list:
                if attr_name == attr['attr_name'] or attr_name == 'all':
                    if 'attr_devtype' in attr.keys() and attr['attr_devtype'] == "gpio":
                        # Check and enable the gpio from class
                        attr_path = self.get_gpio_attr_path(self.data[attr['attr_devname']], attr['attr_offset'])
                        if (os.path.exists(attr_path)):
                            if attr_path not in self.data_sysfs_obj[KEY]:
                                self.data_sysfs_obj[KEY].append(attr_path)
                            ret += attr_path + '\n'
                    else:
                        if 'drv_attr_name' in attr.keys():
                            real_name = attr['drv_attr_name']
                        else:
                            real_name = attr['attr_name']

                        dsysfs_path = self.show_device_sysfs(dev, ops) + \
                            "/%d-00%x" % (int(dev['i2c']['topo_info']['parent_bus'], 0),
                                          int(dev['i2c']['topo_info']['dev_addr'], 0)) + \
                            "/%s" % real_name
                        if dsysfs_path not in self.data_sysfs_obj[KEY]:
                            self.data_sysfs_obj[KEY].append(dsysfs_path)
                            ret += dsysfs_path+"\n"
        return ret

    def show_attr_psu_device(self, dev, ops):
        return self.show_attr_psu_i2c_device(dev, ops)

    def show_attr_fan_device(self, dev, ops):
        ret = ""
        attr_name = ops['attr']
        attr_list = dev['i2c']['attr_list']
        KEY = "fan"
        dsysfs_path = ""

        if KEY not in self.data_sysfs_obj:
            self.data_sysfs_obj[KEY] = []

        for attr in attr_list:
            if attr_name == attr['attr_name'] or attr_name == 'all':
                if 'attr_devtype' in attr.keys() and attr['attr_devtype'] == "gpio":
                    # Check and enable the gpio from class
                    attr_path = self.get_gpio_attr_path(self.data[attr['attr_devname']], attr['attr_offset'])
                    if (os.path.exists(attr_path)):
                        if attr_path not in self.data_sysfs_obj[KEY]:
                            self.data_sysfs_obj[KEY].append(attr_path)
                        ret += attr_path + '\n'
                else:
                    if 'drv_attr_name' in attr.keys():
                        real_name = attr['drv_attr_name']
                    else:
                        real_name = attr['attr_name']

                    dsysfs_path = self.show_device_sysfs(dev, ops) + \
                        "/%d-00%x" % (int(dev['i2c']['topo_info']['parent_bus'], 0),
                                      int(dev['i2c']['topo_info']['dev_addr'], 0)) + \
                        "/%s" % real_name
                    if dsysfs_path not in self.data_sysfs_obj[KEY]:
                        self.data_sysfs_obj[KEY].append(dsysfs_path)
                    ret += dsysfs_path+"\n"
        return ret

    # This is only valid for LM75
    def show_attr_temp_sensor_device(self, dev, ops):
        str = ""
        attr_name = ops['attr']
        attr_list = dev['i2c']['attr_list']
        KEY = "temp-sensors"
        dsysfs_path = ""

        if KEY not in self.data_sysfs_obj:
            self.data_sysfs_obj[KEY] = []

        for attr in attr_list:
            if attr_name == attr['attr_name'] or attr_name == 'all':
                path = self.show_device_sysfs(dev, ops)+"/%d-00%x/" % (int(dev['i2c']['topo_info']['parent_bus'], 0),
                                                                       int(dev['i2c']['topo_info']['dev_addr'], 0))
                if 'drv_attr_name' in attr.keys():
                    real_name = attr['drv_attr_name']
                else:
                    real_name = attr['attr_name']

                if (os.path.exists(path)):
                    full_path = glob.glob(path + 'hwmon/hwmon*/' + real_name)[0]
                    dsysfs_path = full_path
                    if dsysfs_path not in self.data_sysfs_obj[KEY]:
                        self.data_sysfs_obj[KEY].append(dsysfs_path)
                    str += full_path + "\n"
        return str

    def show_attr_sysstatus_device(self, dev, ops):
        ret = ""
        attr_name = ops['attr']
        attr_list = dev['attr_list']
        KEY = "sys-status"
        dsysfs_path = ""

        if KEY not in self.data_sysfs_obj:
            self.data_sysfs_obj[KEY] = []

        for attr in attr_list:
            if attr_name == attr['attr_name'] or attr_name == 'all':
                dsysfs_path = "/sys/kernel/pddf/devices/sysstatus/sysstatus_data/" + attr['attr_name']
                if dsysfs_path not in self.data_sysfs_obj[KEY]:
                    self.data_sysfs_obj[KEY].append(dsysfs_path)
                ret += dsysfs_path+"\n"
        return ret

    def show_attr_xcvr_i2c_device(self, dev, ops):
        target = ops['target']
        attr_name = ops['attr']
        ret = ""
        dsysfs_path = ""
        KEY = "xcvr"
        if KEY not in self.data_sysfs_obj:
            self.data_sysfs_obj[KEY] = []

        if target == 'all' or target == dev['dev_info']['virt_parent']:
            attr_list = dev['i2c']['attr_list']
            for attr in attr_list:
                if attr_name == attr['attr_name'] or attr_name == 'all':
                    if 'attr_devtype' in attr.keys() and attr['attr_devtype'] == "gpio":
                        # Check and enable the gpio from class
                        attr_path = self.get_gpio_attr_path(self.data[attr['attr_devname']], attr['attr_offset'])
                        if (os.path.exists(attr_path)):
                            if attr_path not in self.data_sysfs_obj[KEY]:
                                self.data_sysfs_obj[KEY].append(attr_path)
                            ret += attr_path + '\n'
                    else:
                        if 'drv_attr_name' in attr.keys():
                            real_name = attr['drv_attr_name']
                        else:
                            real_name = attr['attr_name']

                        dsysfs_path = self.show_device_sysfs(dev, ops) + \
                            "/%d-00%x" % (int(dev['i2c']['topo_info']['parent_bus'], 0),
                                          int(dev['i2c']['topo_info']['dev_addr'], 0)) + \
                            "/%s" % real_name
                        if dsysfs_path not in self.data_sysfs_obj[KEY]:
                            self.data_sysfs_obj[KEY].append(dsysfs_path)
                            ret += dsysfs_path+"\n"
        return ret

    def show_attr_xcvr_device(self, dev, ops):
        return self.show_attr_xcvr_i2c_device(dev, ops)

    def show_attr_cpld_device(self, dev, ops):
        ret = ""
        KEY = "cpld"
        if KEY not in self.data_sysfs_obj:
            self.data_sysfs_obj[KEY] = []

        return ret

    ###################################################################################################################
    #   SHOW DEFS
    ###################################################################################################################

    def check_led_cmds(self, key, ops):
        name = ops['target']+'_LED'
        if (ops['target'] == 'config' or ops['attr'] == 'all') or \
                (name == self.data[key]['dev_info']['device_name'] and
                 ops['attr'] == self.data[key]['dev_attr']['index']):
            return (True)
        else:
            return (False)

    def dump_sysfs_obj(self, obj, key_type):
        if (key_type == 'keys'):
            for key in obj.keys():
                print(key)
            return

        for key in obj:
            if (key == key_type or key_type == 'all'):
                print(key+":")
                for entry in obj[key]:
                    print("\t"+entry)

    def add_list_sysfs_obj(self, obj, KEY, list):
        for sysfs in list:
            if sysfs not in obj[KEY]:
                obj[KEY].append(sysfs)

    def sysfs_attr(self, key, value, path, obj, obj_key):
        sysfs_path = "/sys/kernel/%s/%s" % (path, key)
        if sysfs_path not in obj[obj_key]:
            obj[obj_key].append(sysfs_path)

    def sysfs_device(self, attr, path, obj, obj_key):
        for key in attr.keys():
            sysfs_path = "/sys/kernel/%s/%s" % (path, key)
            if sysfs_path not in obj[obj_key]:
                obj[obj_key].append(sysfs_path)

    def show_eeprom_device(self, dev, ops):
        return

    def show_mux_device(self, dev, ops):
        KEY = 'mux'
        if KEY not in self.sysfs_obj:
            self.sysfs_obj[KEY] = []
            self.sysfs_device(dev['i2c']['topo_info'], "pddf/devices/mux", self.sysfs_obj, KEY)
            self.sysfs_device(dev['i2c']['dev_attr'], "pddf/devices/mux", self.sysfs_obj, KEY)
            sysfs_path = "/sys/kernel/pddf/devices/mux/dev_ops"
            if sysfs_path not in self.sysfs_obj[KEY]:
                self.sysfs_obj[KEY].append(sysfs_path)
            list = ['/sys/kernel/pddf/devices/mux/i2c_type',
                    '/sys/kernel/pddf/devices/mux/i2c_name',
                    '/sys/kernel/pddf/devices/mux/error']
            self.add_list_sysfs_obj(self.sysfs_obj, KEY, list)

    def show_gpio_device(self, dev, ops):
        KEY = 'gpio'
        if KEY not in self.sysfs_obj:
            self.sysfs_obj[KEY] = []
            self.sysfs_device(dev['i2c']['topo_info'], "pddf/devices/gpio", self.sysfs_obj, KEY)
            self.sysfs_device(dev['i2c']['dev_attr'], "pddf/devices/gpio", self.sysfs_obj, KEY)
            sysfs_path = "/sys/kernel/pddf/devices/gpio/dev_ops"
            if sysfs_path not in self.sysfs_obj[KEY]:
                self.sysfs_obj[KEY].append(sysfs_path)
            list = ['/sys/kernel/pddf/devices/gpio/i2c_type',
                    '/sys/kernel/pddf/devices/gpio/i2c_name',
                    '/sys/kernel/pddf/devices/gpio/error']
            self.add_list_sysfs_obj(self.sysfs_obj, KEY, list)

    def show_psu_i2c_device(self, dev, ops):
        KEY = 'psu'
        path = 'pddf/devices/psu/i2c'
        if dev['i2c']['topo_info']['dev_type'] in self.data['PLATFORM']['pddf_dev_types']['PSU']:
            if KEY not in self.sysfs_obj:
                self.sysfs_obj[KEY] = []
                self.sysfs_device(dev['i2c']['topo_info'], path, self.sysfs_obj, KEY)
                sysfs_path = "/sys/kernel/pddf/devices/psu/i2c/psu_idx"
                self.sysfs_obj[KEY].append(sysfs_path)

                for attr in dev['i2c']['attr_list']:
                    self.sysfs_device(attr, "pddf/devices/psu/i2c", self.sysfs_obj, KEY)
                    sysfs_path = "/sys/kernel/pddf/devices/psu/i2c/dev_ops"
                    if sysfs_path not in self.sysfs_obj[KEY]:
                        self.sysfs_obj[KEY].append(sysfs_path)
                list = ['/sys/kernel/pddf/devices/psu/i2c/i2c_type',
                        '/sys/kernel/pddf/devices/fan/i2c/i2c_name',
                        '/sys/kernel/pddf/devices/psu/i2c/error',
                        '/sys/kernel/pddf/devices/psu/i2c/attr_ops']
                self.add_list_sysfs_obj(self.sysfs_obj, KEY, list)

    def show_psu_device(self, dev, ops):
        self.show_psu_i2c_device(dev, ops)
        return

    def show_client_device(self):
        KEY = 'client'
        if KEY not in self.sysfs_obj:
            self.sysfs_obj[KEY] = []
            list = ['/sys/kernel/pddf/devices/showall']
            self.add_list_sysfs_obj(self.sysfs_obj, KEY, list)

    def show_fan_device(self, dev, ops):
        KEY = 'fan'
        path = 'pddf/devices/fan/i2c'
        if dev['i2c']['topo_info']['dev_type'] in self.data['PLATFORM']['pddf_dev_types']['FAN']:
            if KEY not in self.sysfs_obj:
                self.sysfs_obj[KEY] = []

                self.sysfs_device(dev['i2c']['topo_info'], path, self.sysfs_obj, KEY)
                self.sysfs_device(dev['i2c']['dev_attr'], path, self.sysfs_obj, KEY)
                for attr in dev['i2c']['attr_list']:
                    self.sysfs_device(attr, path, self.sysfs_obj, KEY)
                list = ['/sys/kernel/pddf/devices/fan/i2c/i2c_type',
                        '/sys/kernel/pddf/devices/fan/i2c/i2c_name',
                        '/sys/kernel/pddf/devices/fan/i2c/error',
                        '/sys/kernel/pddf/devices/fan/i2c/attr_ops',
                        '/sys/kernel/pddf/devices/fan/i2c/dev_ops']
                self.add_list_sysfs_obj(self.sysfs_obj, KEY, list)

    def show_temp_sensor_device(self, dev, ops):
        return

    def show_sysstatus_device(self, dev, ops):
        KEY = 'sysstatus'
        if KEY not in self.sysfs_obj:
            self.sysfs_obj[KEY] = []
            for attr in dev['attr_list']:
                self.sysfs_device(attr, "pddf/devices/sysstatus", self.sysfs_obj, KEY)
                sysfs_path = "/sys/kernel/pddf/devices/sysstatus/attr_ops"
                if sysfs_path not in self.sysfs_obj[KEY]:
                    self.sysfs_obj[KEY].append(sysfs_path)

    def show_xcvr_i2c_device(self, dev, ops):
        KEY = 'xcvr'
        if dev['i2c']['topo_info']['dev_type'] in self.data['PLATFORM']['pddf_dev_types']['PORT_MODULE']:
            if KEY not in self.sysfs_obj:
                self.sysfs_obj[KEY] = []
                self.sysfs_device(dev['i2c']['topo_info'], "pddf/devices/xcvr/i2c", self.sysfs_obj, KEY)

                for attr in dev['i2c']['attr_list']:
                    self.sysfs_device(attr, "pddf/devices/xcvr/i2c", self.sysfs_obj, KEY)
                    sysfs_path = "/sys/kernel/pddf/devices/xcvr/i2c/dev_ops"
                    if sysfs_path not in self.sysfs_obj[KEY]:
                        self.sysfs_obj[KEY].append(sysfs_path)
                list = ['/sys/kernel/pddf/devices/xcvr/i2c/i2c_type',
                        '/sys/kernel/pddf/devices/xcvr/i2c/i2c_name',
                        '/sys/kernel/pddf/devices/xcvr/i2c/error',
                        '/sys/kernel/pddf/devices/xcvr/i2c/attr_ops']
                self.add_list_sysfs_obj(self.sysfs_obj, KEY, list)

    def show_xcvr_device(self, dev, ops):
        self.show_xcvr_i2c_device(dev, ops)
        return

    def show_cpld_device(self, dev, ops):
        KEY = 'cpld'
        if dev['i2c']['topo_info']['dev_type'] in self.data['PLATFORM']['pddf_dev_types']['CPLD']:
            if KEY not in self.sysfs_obj:
                self.sysfs_obj[KEY] = []
                self.sysfs_device(dev['i2c']['topo_info'], "pddf/devices/cpld", self.sysfs_obj, KEY)
                sysfs_path = "/sys/kernel/pddf/devices/cpld/dev_ops"
                if sysfs_path not in self.sysfs_obj[KEY]:
                    self.sysfs_obj[KEY].append(sysfs_path)
                list = ['/sys/kernel/pddf/devices/cpld/i2c_type',
                        '/sys/kernel/pddf/devices/cpld/i2c_name',
                        '/sys/kernel/pddf/devices/cpld/error']
                self.add_list_sysfs_obj(self.sysfs_obj, KEY, list)

    def show_led_platform_device(self, key, ops):
        if ops['attr'] == 'all' or ops['attr'] == 'PLATFORM':
            KEY = 'platform'
            if KEY not in self.sysfs_obj:
                self.sysfs_obj[KEY] = []
                path = 'pddf/devices/platform'
                self.sysfs_attr('num_psus', self.data['PLATFORM']['num_psus'], path, self.sysfs_obj, KEY)
                self.sysfs_attr('num_fantrays', self.data['PLATFORM']['num_fantrays'], path, self.sysfs_obj, KEY)

    def show_led_device(self, key, ops):
        if self.check_led_cmds(key, ops):
            KEY = 'led'
            if KEY not in self.sysfs_obj:
                self.sysfs_obj[KEY] = []
                path = "pddf/devices/led"
                for attr in self.data[key]['i2c']['attr_list']:
                    self.sysfs_attr('device_name', self.data[key]['dev_info']['device_name'], path, self.sysfs_obj, KEY)
                    self.sysfs_attr('swpld_addr', self.data[key]['dev_info']['device_name'], path, self.sysfs_obj, KEY)
                    self.sysfs_attr('swpld_addr_offset', self.data[key]['dev_info']['device_name'], path,
                                    self.sysfs_obj, KEY)
                    self.sysfs_device(self.data[key]['dev_attr'], path, self.sysfs_obj, KEY)
                    for attr_key in attr.keys():
                        attr_path = "pddf/devices/led/" + attr['attr_name']
                        if (attr_key != 'attr_name' and attr_key != 'swpld_addr' and attr_key != 'swpld_addr_offset'):
                            self.sysfs_attr(attr_key, attr[attr_key], attr_path, self.sysfs_obj, KEY)
                sysfs_path = "/sys/kernel/pddf/devices/led/dev_ops"
                if sysfs_path not in self.sysfs_obj[KEY]:
                    self.sysfs_obj[KEY].append(sysfs_path)
                list = ['/sys/kernel/pddf/devices/led/cur_state/color',
                        '/sys/kernel/pddf/devices/led/cur_state/color_state']
                self.add_list_sysfs_obj(self.sysfs_obj, KEY, list)

    def validate_xcvr_device(self, dev, ops):
        devtype_list = ['optoe1', 'optoe2']
        dev_attribs = ['xcvr_present', 'xcvr_reset', 'xcvr_intr_status', 'xcvr_lpmode']
        ret_val = "xcvr validation failed"

        if dev['i2c']['topo_info']['dev_type'] in devtype_list:
            for attr in dev['i2c']['attr_list']:
                if 'attr_name' in attr.keys() and 'eeprom' in attr.values():
                    ret_val = "xcvr validation success"
                else:
                    print("xcvr validation Failed")
                    return

        elif dev['i2c']['topo_info']['dev_type'] in self.data['PLATFORM']['pddf_dev_types']['PORT_MODULE']:
            for attr in dev['i2c']['attr_list']:
                if attr.get("attr_name") in dev_attribs:
                    ret_val = "Success"
                else:
                    print("xcvr validation Failed")
                    return
        print(ret_val)

    def validate_eeprom_device(self, dev, ops):
        devtype_list = ['24c02']
        dev_access_mode = ['BLOCK', 'BYTE']
        dev_attribs = ['eeprom']
        ret_val = "eeprom failed"

        if dev['i2c']['topo_info']['dev_type'] in devtype_list:
            if dev['i2c']['dev_attr']['access_mode'] in dev_access_mode:
                for attr in dev['i2c']['attr_list']:
                    if attr.get("attr_name") in dev_attribs:
                        ret_val = "eeprom success"
        print(ret_val)

    def validate_mux_device(self, dev, ops):
        devtype_list = ['pca9548', 'pca954x']
        dev_channels = ["0", "1", "2", "3", "4", "5", "6", "7"]
        ret_val = "mux failed"

        if dev['i2c']['topo_info']['dev_type'] in devtype_list:
            for attr in dev['i2c']['channel']:
                if attr.get("chn") in dev_channels:
                    ret_val = "Mux success"
        print(ret_val)

    def validate_cpld_device(self, dev, ops):
        devtype_list = ['i2c_cpld']
        ret_val = "cpld failed"

        if dev['i2c']['topo_info']['dev_type'] in devtype_list:
            ret_val = "cpld success"
        print(ret_val)

    def validate_sysstatus_device(self, dev, ops):
        dev_attribs = ['board_info', 'cpld1_version', 'power_module_status', 'system_reset5',
                       'system_reset6', 'system_reset7', 'misc1', 'cpld2_version', 'cpld3_version'
                       ]
        ret_val = "sysstatus failed"

        if dev['dev_info']['device_type'] == "SYSSTAT":
            for attr in dev['attr_list']:
                if attr.get("attr_name") in dev_attribs:
                    ret_val = "sysstatus success"
        print(ret_val)

    def validate_temp_sensor_device(self, dev, ops):
        devtype_list = ['lm75']
        dev_attribs = ['temp1_max', 'temp1_max_hyst', 'temp1_input']
        ret_val = "temp sensor failed"

        if dev['dev_info']['device_type'] == "TEMP_SENSOR":
            if dev['i2c']['topo_info']['dev_type'] in devtype_list:
                for attr in dev['i2c']['attr_list']:
                    if attr.get("attr_name") in dev_attribs:
                        ret_val = "tempsensor success"
        print(ret_val)

    def validate_fan_device(self, dev, ops):
        ret_val = "fan failed"

        if dev['i2c']['topo_info']['dev_type'] in self.data['PLATFORM']['pddf_dev_types']['FAN']:
            if dev['i2c']['dev_attr']['num_fan'] is not None:
                ret_val = "fan success"

        print(ret_val)

    def validate_psu_device(self, dev, ops):
        dev_attribs = ['psu_present', 'psu_model_name', 'psu_power_good', 'psu_mfr_id', 'psu_serial_num',
                       'psu_fan_dir', 'psu_v_out', 'psu_i_out', 'psu_p_out', 'psu_fan1_speed_rpm'
                       ]
        ret_val = "psu failed"

        if dev['i2c']['topo_info']['dev_type'] in self.data['PLATFORM']['pddf_dev_types']['PSU']:
            for attr in dev['i2c']['attr_list']:
                if attr.get("attr_name") in dev_attribs:
                    if attr.get("attr_devaddr") is not None:
                        if attr.get("attr_offset") is not None:
                            if attr.get("attr_mask") is not None:
                                if attr.get("attr_len") is not None:
                                    ret_val = "psu success"
                else:
                    ret_val = "psu failed"

        print(ret_val)

    ###################################################################################################################
    #  SPYTEST
    ###################################################################################################################
    def verify_attr(self, key, attr, path):
        node = "/sys/kernel/%s/%s" % (path, key)
        try:
            with open(node, 'r') as f:
                status = f.read()
        except IOError:
            print("PDDF_VERIFY_ERR: IOError: node:%s key:%s" % (node, key))
            return

        status = status.rstrip("\n\r")
        if attr[key] != status:
            print("PDDF_VERIFY_ERR: node: %s switch:%s" % (node, status))

    def verify_device(self, attr, path, ops):
        for key in attr.keys():
            self.verify_attr(key, attr, path)

    def get_led_device(self, device_name):
        self.create_attr('device_name', self.data[device_name]['dev_info']['device_name'], "pddf/devices/led")
        self.create_attr('index', self.data[device_name]['dev_attr']['index'], "pddf/devices/led")
        cmd = "echo 'verify'  > /sys/kernel/pddf/devices/led/dev_ops"
        self.runcmd(cmd)

    def validate_sysfs_creation(self, obj, validate_type):
        dir = '/sys/kernel/pddf/devices/'+validate_type
        if (os.path.exists(dir) or validate_type == 'client'):
            for sysfs in obj[validate_type]:
                if not os.path.exists(sysfs):
                    print("[SYSFS FILE] " + sysfs + ": does not exist")
        else:
            print("[SYSFS DIR] " + dir + ": does not exist")

    def validate_dsysfs_creation(self, obj, validate_type):
        if validate_type in obj.keys():
            # There is a possibility that some components dont have any device-self.data attr
            if not obj[validate_type]:
                print("[SYSFS ATTR] for " + validate_type + ": empty")
            else:
                for sysfs in obj[validate_type]:
                    if not os.path.exists(sysfs):
                        print("[SYSFS FILE] " + sysfs + ": does not exist")
        else:
            print("[SYSFS DIR] " + dir + ": not configured")

    def verify_sysfs_data(self, verify_type):
        if (verify_type == 'LED'):
            for key in self.data.keys():
                if key != 'PLATFORM':
                    attr = self.data[key]['dev_info']
                    if attr['device_type'] == 'LED':
                        self.get_led_device(key)
                        self.verify_attr('device_name', self.data[key]['dev_info'], "pddf/devices/led")
                        self.verify_attr('index', self.data[key]['dev_attr'], "pddf/devices/led")
                        for attr in self.data[key]['i2c']['attr_list']:
                            path = "pddf/devices/led/" + attr['attr_name']
                            for entry in attr.keys():
                                if (entry != 'attr_name' and entry != 'swpld_addr' and entry != 'swpld_addr_offset'):
                                    self.verify_attr(entry, attr, path)
                                if (entry == 'swpld_addr' or entry == 'swpld_addr_offset'):
                                    self.verify_attr(entry, attr, 'pddf/devices/led')

    def schema_validation(self, validate_type):
        process_validate_type = 0
        for key in self.data.keys():
            if (key != 'PLATFORM'):
                temp_obj = {}
                schema_list = []
                try:
                    device_type = self.data[key]["dev_info"]["device_type"]
                except Exception as e:
                    print("dev_info or device_type ERROR: " + key)
                    print(e)

                if validate_type == 'mismatch':
                    process_validate_type = 1
                    device_type = "PSU"
                    schema_file = "/usr/local/bin/schema/FAN.schema"
                    schema_list.append(schema_file)
                elif validate_type == 'missing':
                    process_validate_type = 1
                    schema_file = "/usr/local/bin/schema/PLATFORM.schema"
                    schema_list.append(schema_file)

                elif validate_type == 'empty':
                    process_validate_type = 1
                    if not device_type:
                        print("Empty device_type for " + key)
                        continue
                elif (validate_type == 'all' or validate_type == device_type):
                    process_validate_type = 1
                    if "bmc" in self.data[key].keys():
                        schema_file = "/usr/local/bin/schema/"+device_type + "_BMC.schema"
                        schema_list.append(schema_file)

                    if "i2c" in self.data[key].keys():
                        schema_file = "/usr/local/bin/schema/"+device_type + ".schema"
                        schema_list.append(schema_file)
                if device_type:
                    temp_obj[device_type] = self.data[key]
                    for schema_file in schema_list:
                        if (os.path.exists(schema_file)):
                            print("Validate " + schema_file + ";" + key)
                            json_data = json.dumps(temp_obj)
                            with open(schema_file, 'r') as f:
                                schema = json.load(f)
                            try:
                                validate(temp_obj, schema)
                            except Exception as e:
                                print("Validation ERROR: " + schema_file + ";" + key)
                                if validate_type == 'mismatch':
                                    return
                                else:
                                    print(e)
                        else:
                            print("ERROR Missing File: " + schema_file)
        if not process_validate_type:
            print("device_type: " + validate_type + " not configured")

    def modules_validation(self, validate_type):
        kos = []
        supported_type = False
        module_validation_status = []

        if validate_type == "bmc":
            kos = ['ipmi_devintf', 'ipmi_si', 'ipmi_msghandler']
            validate_type = 'ipmi'
        else:
            # generate the KOS list from pddf device JSON file
            kos.extend(self.data['PLATFORM']['pddf_kos'])

            if 'custom_kos' in self.data['PLATFORM']:
                kos.extend(self.data['PLATFORM']['custom_kos'])

        for mod in kos:
            if validate_type in mod or validate_type == "pddf":
                supported_type = True
                cmd = "lsmod | grep " + mod
                try:
                    subprocess.check_output(cmd, shell=True)
                except Exception as e:
                    module_validation_status.append(mod)
        if supported_type:
            if module_validation_status:
                module_validation_status.append(":ERROR not loaded")
                print(str(module_validation_status)[1:-1])
            else:
                print("Loaded")
        else:
            print(validate_type + " not configured")

    ###################################################################################################################
    #   PARSE DEFS
    ###################################################################################################################

    def psu_parse(self, dev, ops):
        parse_str = ""
        ret = ""
        for ifce in dev['i2c']['interface']:
            ret = getattr(self, ops['cmd']+"_psu_device")(self.data[ifce['dev']], ops)
            if ret is not None:
                if str(ret).isdigit():
                    if ret != 0:
                        # in case if 'create' functions
                        print("{}_psu_device failed".format(ops['cmd']))
                        return ret
                    else:
                        pass
                else:
                    # in case of 'show_attr' functions
                    parse_str += ret
        return parse_str

    def fan_parse(self, dev, ops):
        parse_str = ""
        ret = getattr(self, ops['cmd']+"_fan_device")(dev, ops)
        if ret is not None:
            if str(ret).isdigit():
                if ret != 0:
                    # in case if 'create' functions
                    print("{}_fan_device failed".format(ops['cmd']))
                    return ret
                else:
                    pass
            else:
                # in case of 'show_attr' functions
                parse_str += ret

        return parse_str

    def temp_sensor_parse(self, dev, ops):
        parse_str = ""
        ret = getattr(self, ops['cmd']+"_temp_sensor_device")(dev, ops)
        if ret is not None:
            if str(ret).isdigit():
                if ret != 0:
                    # in case if 'create' functions
                    print("{}_temp_sensor_device failed".format(ops['cmd']))
                    return ret
                else:
                    pass
            else:
                # in case of 'show_attr' functions
                parse_str += ret

        return parse_str

    def cpld_parse(self, dev, ops):
        parse_str = ""
        ret = getattr(self, ops['cmd']+"_cpld_device")(dev, ops)
        if ret is not None:
            if str(ret).isdigit():
                if ret != 0:
                    # in case if 'create' functions
                    print("{}_cpld_device failed".format(ops['cmd']))
                    return ret
                else:
                    pass
            else:
                # in case of 'show_attr' functions
                parse_str += ret

        return parse_str

    def sysstatus_parse(self, dev, ops):
        parse_str = ""
        ret = getattr(self, ops['cmd']+"_sysstatus_device")(dev, ops)
        if ret is not None:
            if str(ret).isdigit():
                if ret != 0:
                    # in case if 'create' functions
                    print("{}_sysstatus_device failed".format(ops['cmd']))
                    return ret
                else:
                    pass
            else:
                # in case of 'show_attr' functions
                parse_str += ret

        return parse_str

    def gpio_parse(self, dev, ops):
        parse_str = ""
        ret = getattr(self, ops['cmd']+"_gpio_device")(dev, ops)
        if ret is not None:
            if str(ret).isdigit():
                if ret != 0:
                    # in case if 'create' functions
                    print("{}_temp_sensor_device failed".format(ops['cmd']))
                    return ret
                else:
                    pass
            else:
                # in case of 'show_attr' functions
                parse_str += ret

        return parse_str

    def mux_parse(self, dev, ops):
        parse_str = ""
        ret = getattr(self, ops['cmd']+"_mux_device")(dev, ops)
        if ret is not None:
            if str(ret).isdigit():
                if ret != 0:
                    # in case if 'create' functions
                    print("{}_mux_device() cmd failed".format(ops['cmd']))
                    return ret
                else:
                    pass
            else:
                parse_str += ret

        for ch in dev['i2c']['channel']:
            ret = self.dev_parse(self.data[ch['dev']], ops)
            if ret is not None:
                if str(ret).isdigit():
                    if ret != 0:
                        # in case if 'create' functions
                        return ret
                    else:
                        pass
                else:
                    parse_str += ret
        return parse_str

    def mux_parse_reverse(self, dev, ops):
        parse_str = ""
        for ch in reversed(dev['i2c']['channel']):
            ret = self.dev_parse(self.data[ch['dev']], ops)
            if ret is not None:
                if str(ret).isdigit():
                    if ret != 0:
                        # in case if 'create' functions
                        return ret
                    else:
                        pass
                else:
                    parse_str += ret

        ret = getattr(self, ops['cmd']+"_mux_device")(dev, ops)
        if ret is not None:
            if str(ret).isdigit():
                if ret != 0:
                    # in case if 'create' functions
                    print("{}_mux_device() cmd failed".format(ops['cmd']))
                    return ret
                else:
                    pass
            else:
                parse_str += ret

        return parse_str

    def eeprom_parse(self, dev, ops):
        parse_str = ""
        ret = getattr(self, ops['cmd']+"_eeprom_device")(dev, ops)
        if ret is not None:
            if str(ret).isdigit():
                if ret != 0:
                    # in case if 'create' functions
                    print("{}_eeprom_device() cmd failed".format(ops['cmd']))
                    return ret
                else:
                    pass
            else:
                parse_str += ret

        return parse_str

    def optic_parse(self, dev, ops):
        parse_str = ""
        ret = ""
        for ifce in dev['i2c']['interface']:
            ret = getattr(self, ops['cmd']+"_xcvr_device")(self.data[ifce['dev']], ops)
            if ret is not None:
                if str(ret).isdigit():
                    if ret != 0:
                        # in case if 'create' functions
                        print("{}_eeprom_device() cmd failed".format(ops['cmd']))
                        return ret
                    else:
                        pass
                else:
                    parse_str += ret
        return parse_str

    def cpu_parse(self, bus, ops):
        parse_str = ""
        for dev in bus['i2c']['CONTROLLERS']:
            dev1 = self.data[dev['dev']]
            for d in dev1['i2c']['DEVICES']:
                ret = self.dev_parse(self.data[d['dev']], ops)
                if ret is not None:
                    if str(ret).isdigit():
                        if ret != 0:
                            # in case if 'create' functions
                            return ret
                        else:
                            pass
                    else:
                        parse_str += ret
        return parse_str

    def cpu_parse_reverse(self, bus, ops):
        parse_str = ""
        for dev in reversed(bus['i2c']['CONTROLLERS']):
            dev1 = self.data[dev['dev']]
            for d in dev1['i2c']['DEVICES']:
                ret = self.dev_parse(self.data[d['dev']], ops)
                if ret is not None:
                    if str(ret).isdigit():
                        if ret != 0:
                            # in case if 'create' functions
                            return ret
                        else:
                            pass
                    else:
                        parse_str += ret
        return parse_str

    def dev_parse(self, dev, ops):
        attr = dev['dev_info']
        if attr['device_type'] == 'CPU':
            if ops['cmd'] == 'delete':
                return self.cpu_parse_reverse(dev, ops)
            else:
                return self.cpu_parse(dev, ops)

        if attr['device_type'] == 'EEPROM':
            return self.eeprom_parse(dev, ops)

        if attr['device_type'] == 'MUX':
            if ops['cmd'] == 'delete':
                return self.mux_parse_reverse(dev, ops)
            else:
                return self.mux_parse(dev, ops)

        if attr['device_type'] == 'GPIO':
            return self.gpio_parse(dev, ops)

        if attr['device_type'] == 'PSU':
            return self.psu_parse(dev, ops)

        if attr['device_type'] == 'FAN':
            return self.fan_parse(dev, ops)

        if attr['device_type'] == 'TEMP_SENSOR':
            return self.temp_sensor_parse(dev, ops)

        if attr['device_type'] == 'SFP' or attr['device_type'] == 'QSFP' or \
                attr['device_type'] == 'SFP28' or attr['device_type'] == 'QSFP28' or \
                attr['device_type'] == 'QSFP-DD':
            return self.optic_parse(dev, ops)

        if attr['device_type'] == 'CPLD':
            return self.cpld_parse(dev, ops)

        if attr['device_type'] == 'SYSSTAT':
            return self.sysstatus_parse(dev, ops)

    def is_supported_sysled_state(self, sysled_name, sysled_state):
        if sysled_name not in self.data.keys():
            return False, "[FAILED] " + sysled_name + " is not configured"
        for attr in self.data[sysled_name]['i2c']['attr_list']:
            if attr['attr_name'] == sysled_state:
                return True, "supported"
        return False,  "[FAILED]: Invalid color"

    def create_attr(self, key, value, path):
        cmd = "echo '%s' > /sys/kernel/%s/%s" % (value,  path, key)
        self.runcmd(cmd)

    def create_led_platform_device(self, key, ops):
        if ops['attr'] == 'all' or ops['attr'] == 'PLATFORM':
            path = 'pddf/devices/platform'
            self.create_attr('num_psus', self.data['PLATFORM']['num_psus'], path)
            self.create_attr('num_fantrays', self.data['PLATFORM']['num_fantrays'], path)

    def create_led_device(self, key, ops):
        if ops['attr'] == 'all' or ops['attr'] == self.data[key]['dev_info']['device_name']:
            path = "pddf/devices/led"
            for attr in self.data[key]['i2c']['attr_list']:
                self.create_attr('device_name', self.data[key]['dev_info']['device_name'], path)
                self.create_device(self.data[key]['dev_attr'], path, ops)
                for attr_key in attr.keys():
                    if (attr_key == 'swpld_addr_offset' or attr_key == 'swpld_addr'):
                        self.create_attr(attr_key, attr[attr_key], path)
                    elif (attr_key != 'attr_name' and attr_key != 'descr' and attr_key != 'attr_devtype' and
                            attr_key != 'attr_devname'):
                        state_path = path+'/state_attr'
                        self.create_attr(attr_key, attr[attr_key], state_path)
                cmd = "echo '" + attr['attr_name']+"' > /sys/kernel/pddf/devices/led/dev_ops"
                self.runcmd(cmd)

    def led_parse(self, ops):
        getattr(self, ops['cmd']+"_led_platform_device")("PLATFORM", ops)
        for key in self.data.keys():
            if key != 'PLATFORM' and 'dev_info' in self.data[key]:
                attr = self.data[key]['dev_info']
                if attr['device_type'] == 'LED':
                    getattr(self, ops['cmd']+"_led_device")(key, ops)

    def get_device_list(self, list, type):
        for key in self.data.keys():
            if key != 'PLATFORM' and 'dev_info' in self.data[key]:
                attr = self.data[key]['dev_info']
                if attr['device_type'] == type:
                    list.append(self.data[key])

    def create_pddf_devices(self):
        self.led_parse({"cmd": "create", "target": "all", "attr": "all"})
        create_ret = 0
        create_ret = self.dev_parse(self.data['SYSTEM'], {"cmd": "create", "target": "all", "attr": "all"})
        if create_ret != 0:
            return create_ret
        if 'SYSSTATUS' in self.data:
            create_ret = self.dev_parse(self.data['SYSSTATUS'], {"cmd": "create", "target": "all", "attr": "all"})
            if create_ret != 0:
                return create_ret

    def delete_pddf_devices(self):
        self.dev_parse(self.data['SYSTEM'], {"cmd": "delete", "target": "all", "attr": "all"})
        if 'SYSSTATUS' in self.data:
            self.dev_parse(self.data['SYSSTATUS'], {"cmd": "delete", "target": "all", "attr": "all"})

    def populate_pddf_sysfsobj(self):
        self.dev_parse(self.data['SYSTEM'], {"cmd": "show", "target": "all", "attr": "all"})
        if 'SYSSTATUS' in self.data:
            self.dev_parse(self.data['SYSSTATUS'], {"cmd": "show", "target": "all", "attr": "all"})
        self.led_parse({"cmd": "show", "target": "all", "attr": "all"})
        self.show_client_device()

    def cli_dump_dsysfs(self, component):
        self.dev_parse(self.data['SYSTEM'], {"cmd": "show_attr", "target": "all", "attr": "all"})
        if 'SYSSTATUS' in self.data:
            self.dev_parse(self.data['SYSSTATUS'], {"cmd": "show_attr", "target": "all", "attr": "all"})
        if component in self.data_sysfs_obj:
            return self.data_sysfs_obj[component]
        else:
            return None

    def validate_pddf_devices(self, *args):
        self.populate_pddf_sysfsobj()
        v_ops = {'cmd': 'validate', 'target': 'all', 'attr': 'all'}
        self.dev_parse(self.data['SYSTEM'], v_ops)

    ###################################################################################################################
    #   BMC APIs
    ###################################################################################################################
    def populate_bmc_cache_db(self, bmc_attr):
        bmc_cmd = str(bmc_attr['bmc_cmd']).strip()

        o_list = subprocess.check_output(bmc_cmd, shell=True).strip().split('\n')
        bmc_cache[bmc_cmd] = {}
        bmc_cache[bmc_cmd]['time'] = time.time()
        for entry in o_list:
            name = entry.split()[0]
            bmc_cache[bmc_cmd][name] = entry

    def non_raw_ipmi_get_request(self, bmc_attr):
        bmc_db_update_time = 1
        value = 'N/A'
        bmc_cmd = str(bmc_attr['bmc_cmd']).strip()
        field_name = str(bmc_attr['field_name']).strip()
        field_pos = int(bmc_attr['field_pos'])-1

        if bmc_cmd not in bmc_cache:
            self.populate_bmc_cache_db(bmc_attr)
        else:
            now = time.time()
            if (int(now - bmc_cache[bmc_cmd]['time']) > bmc_db_update_time):
                self.populate_bmc_cache_db(bmc_attr)

        try:
            data = bmc_cache[bmc_cmd][field_name]
            value = data.split()[field_pos]
        except Exception as e:
            pass

        if 'mult' in bmc_attr.keys() and not value.isalpha():
            if value.isalpha():
                value = 0.0
            value = float(value) * float(bmc_attr['mult'])

        return str(value)

    def raw_ipmi_get_request(self, bmc_attr):
        value = 'N/A'
        cmd = bmc_attr['bmc_cmd'] + " 2>/dev/null"
        if bmc_attr['type'] == 'raw':
            try:
                value = subprocess.check_output(cmd, shell=True).strip()
            except Exception as e:
                pass

            if value != 'N/A':
                value = str(int(value, 16))
            return value

        if bmc_attr['type'] == 'mask':
            mask = int(bmc_attr['mask'].encode('utf-8'), 16)
            try:
                value = subprocess.check_output(cmd, shell=True).strip()
            except Exception as e:
                pass

            if value != 'N/A':
                value = str(int(value, 16) & mask)

            return value

        if bmc_attr['type'] == 'ascii':
            try:
                value = subprocess.check_output(cmd, shell=True)
            except Exception as e:
                pass

            if value != 'N/A':
                tmp = ''.join(chr(int(i, 16)) for i in value.split())
                tmp = "".join(i for i in str(tmp) if unicodedata.category(i)[0] != "C")
                value = str(tmp)

            return (value)

        return value

    def bmc_get_cmd(self, bmc_attr):
        if int(bmc_attr['raw']) == 1:
            value = self.raw_ipmi_get_request(bmc_attr)
        else:
            value = self.non_raw_ipmi_get_request(bmc_attr)
        return (value)

    def non_raw_ipmi_set_request(self, bmc_attr, val):
        value = 'N/A'
        # TODO: Implement it
        return value

    def raw_ipmi_set_request(self, bmc_attr, val):
        value = 'N/A'
        # TODO: Implement this
        return value

    def bmc_set_cmd(self, bmc_attr, val):
        if int(bmc_attr['raw']) == 1:
            value = self.raw_ipmi_set_request(bmc_attr, val)
        else:
            value = self.non_raw_ipmi_set_request(bmc_attr, val)
        return (value)

    # bmc-based attr: return attr obj
    # non-bmc-based attr: return empty obj
    def check_bmc_based_attr(self, device_name, attr_name):
        if device_name in self.data.keys():
            if "bmc" in self.data[device_name].keys() and 'ipmitool' in self.data[device_name]['bmc'].keys():
                attr_list = self.data[device_name]['bmc']['ipmitool']['attr_list']
                for attr in attr_list:
                    if attr['attr_name'].strip() == attr_name.strip():
                        return attr
                # Required attr_name is not supported in BMC object
                return {}
        return None

    def get_attr_name_output(self, device_name, attr_name):
        bmc_attr = self.check_bmc_based_attr(device_name, attr_name)
        output = {"mode": "", "status": ""}

        if bmc_attr is not None:
            if bmc_attr == {}:
                return {}
            output['mode'] = "bmc"
            output['status'] = self.bmc_get_cmd(bmc_attr)
        else:
            output['mode'] = "i2c"
            node = self.get_path(device_name, attr_name)
            if node is None:
                return {}
            try:
                with open(node, 'r') as f:
                    output['status'] = f.read()
            except IOError:
                return {}
        return output

    def set_attr_name_output(self, device_name, attr_name, val):
        bmc_attr = self.check_bmc_based_attr(device_name, attr_name)
        output = {"mode": "", "status": ""}

        if bmc_attr is not None:
            if bmc_attr == {}:
                return {}
            output['mode'] = "bmc"
            output['status'] = False  # No set operation allowed for BMC attributes as they are handled by BMC itself
        else:
            output['mode'] = "i2c"
            node = self.get_path(device_name, attr_name)
            if node is None:
                return {}
            try:
                with open(node, 'w') as f:
                    f.write(str(val))
            except IOError:
                return {}

            output['status'] = True

        return output
