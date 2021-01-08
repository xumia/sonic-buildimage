#!/usr/bin/env python

# All the supported Temperature Sensor SysFS aattributes are
#- temp1_high_crit_threshold
#- temp1_high_threshold
#- temp1_input
#- temp_low_threshold
#- temp1_low_crit_threshold

try:
    from sonic_platform_base.thermal_base import ThermalBase
except ImportError as e:
    raise ImportError(str(e) + "- required module not found")


class PddfThermal(ThermalBase):
    """PDDF generic Thermal class"""
    pddf_obj = {}
    plugin_data = {}

    def __init__(self, index, pddf_data=None, pddf_plugin_data=None):
        if not pddf_data or not pddf_plugin_data:
            raise ValueError('PDDF JSON data error')

        self.pddf_obj = pddf_data
        self.plugin_data = pddf_plugin_data

        self.platform = self.pddf_obj.get_platform()

        self.thermal_index = index + 1
        self.thermal_obj_name = "TEMP{}".format(self.thermal_index)
        self.thermal_obj = self.pddf_obj.data[self.thermal_obj_name]

    def get_name(self):
        if 'dev_attr' in self.thermal_obj.keys():
            if 'display_name' in self.thermal_obj['dev_attr']:
                return str(self.thermal_obj['dev_attr']['display_name'])
        # In case of errors
        return (self.thermal_obj_name)

    def get_temperature(self):
        output = self.pddf_obj.get_attr_name_output(self.thermal_obj_name, "temp1_input")
        if not output:
            return None

        if output['status'].isalpha():
            attr_value = None
        else:
            attr_value = float(output['status'])

        if output['mode'] == 'bmc':
            return attr_value
        else:
            return (attr_value/float(1000))

    def get_high_threshold(self):
        output = self.pddf_obj.get_attr_name_output(self.thermal_obj_name, "temp1_high_threshold")
        if not output:
            return None

        if output['status'].isalpha():
            attr_value = None
        else:
            attr_value = float(output['status'])

        if output['mode'] == 'bmc':
            return attr_value
        else:
            return (attr_value/float(1000))

    def get_low_threshold(self):
        output = self.pddf_obj.get_attr_name_output(self.thermal_obj_name, "temp1_low_threshold")
        if not output:
            return None

        if output['status'].isalpha():
            attr_value = None
        else:
            attr_value = float(output['status'])

        if output['mode'] == 'bmc':
            return attr_value
        else:
            return (attr_value/float(1000))

    def set_high_threshold(self, temperature):
        node = self.pddf_obj.get_path(self.thermal_obj_name, "temp1_high_threshold")
        if node is None:
            print("ERROR %s does not exist" % node)
            return None

        cmd = "echo '%d' > %s" % (temperature * 1000, node)
        os.system(cmd)

        return (True)

    def set_low_threshold(self, temperature):
        node = self.pddf_obj.get_path(self.thermal_obj_name, "temp1_low_threshold")
        if node is None:
            print("ERROR %s does not exist" % node)
            return None
        cmd = "echo '%d' > %s" % (temperature * 1000, node)
        os.system(cmd)

        return (True)

    def get_high_critical_threshold(self):
        """
        Retrieves the high critical threshold temperature of thermal

        Returns:
            A float number, the high critical threshold temperature of thermal in Celsius
            up to nearest thousandth of one degree Celsius, e.g. 30.125
        """
        output = self.pddf_obj.get_attr_name_output(self.thermal_obj_name, "temp1_high_crit_threshold")
        if not output:
            return None

        if output['status'].isalpha():
            attr_value = None
        else:
            attr_value = float(output['status'])

        if output['mode'] == 'bmc':
            return attr_value
        else:
            return (attr_value/float(1000))

    def get_low_critical_threshold(self):
        """
        Retrieves the low critical threshold temperature of thermal

        Returns:
            A float number, the low critical threshold temperature of thermal in Celsius
            up to nearest thousandth of one degree Celsius, e.g. 30.125
        """
        output = self.pddf_obj.get_attr_name_output(self.thermal_obj_name, "temp1_low_crit_threshold")
        if not output:
            return None

        if output['status'].isalpha():
            attr_value = None
        else:
            attr_value = float(output['status'])

        if output['mode'] == 'bmc':
            return attr_value
        else:
            return (attr_value/float(1000))

    # Helper Functions

    def get_temp_label(self):
        if 'bmc' in self.pddf_obj.data[self.thermal_obj_name].keys():
            return None
        else:
            if self.thermal_obj_name in self.pddf_obj.data.keys():
                dev = self.pddf_obj.data[self.thermal_obj_name]
                topo_info = dev['i2c']['topo_info']
                label = "%s-i2c-%d-%x" % (topo_info['dev_type'], int(topo_info['parent_bus'], 0),
                                          int(topo_info['dev_addr'], 0))
                return (label)
            else:
                return None

    def dump_sysfs(self):
        return self.pddf_obj.cli_dump_dsysfs('temp-sensors')
