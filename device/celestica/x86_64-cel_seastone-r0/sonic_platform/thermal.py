#############################################################################
# Celestica
#
# Thermal contains an implementation of SONiC Platform Base API and
# provides the thermal device status which are available in the platform
#
#############################################################################

import os
import re
import os.path

try:
    from sonic_platform_base.thermal_base import ThermalBase
    from .helper import APIHelper
except ImportError as e:
    raise ImportError(str(e) + "- required module not found")

THERMAL_INFO = {
    0: {
        "F2B_max": 50,
        "B2F_max": 55,
        "postion": "asic",
        "name": "Front-panel temp sensor 1",
        "i2c_path": "i2c-5/5-0048/hwmon/hwmon1",    # u4 system-inlet
    },
    1: {
        "F2B_max": 50,
        "B2F_max": 55,
        "postion": "asic",
        "name": "Front-panel temp sensor 2",
        "i2c_path": "i2c-6/6-0049/hwmon/hwmon2",    # u2 system-inlet
    },
    2: {
        "F2B_max": 70,
        "F2B_max_crit": 75,
        "B2F_max": 60,
        "B2F_max_crit": 65,
        "postion": "asic",
        "name": "ASIC temp sensor",
        "i2c_path": "i2c-7/7-004a/hwmon/hwmon3",    # u44 bmc56960-on-board
    },
    3: {
        "F2B_max": 70,
        "F2B_max_crit": 75,
        "B2F_max": 70,
        "B2F_max_crit": 75,
        "postion": "cpu",
        "name": "Rear-panel temp sensor 1",
        "i2c_path": "i2c-14/14-0048/hwmon/hwmon4",  # u9200 cpu-on-board
    },
    4: {
        "F2B_max": 70,
        "B2F_max": 55,
        "postion": "cpu",
        "name": "Rear-panel temp sensor 2",
        "i2c_path": "i2c-15/15-004e/hwmon/hwmon5"   # u9201 system-outlet
    }
}
NULL_VAL = "N/A"
I2C_ADAPTER_PATH = "/sys/class/i2c-adapter"


class Thermal(ThermalBase):
    """Platform-specific Thermal class"""

    SS_CONFIG_PATH = "/usr/share/sonic/device/x86_64-cel_seastone-r0/sensors.conf"

    def __init__(self, thermal_index, airflow):
        self.index = thermal_index
        self._api_helper = APIHelper()
        self._airflow = airflow
        self._thermal_info = THERMAL_INFO[self.index]
        self._hwmon_path = "{}/{}".format(I2C_ADAPTER_PATH,
                                         self._thermal_info["i2c_path"])
        self.name = self.get_name()
        self.postion = self._thermal_info["postion"]
        self.ss_index = 1

    def __get_temp(self, temp_file):
        temp_file_path = os.path.join(self._hwmon_path, temp_file)
        raw_temp = self._api_helper.read_txt_file(temp_file_path)
        temp = float(raw_temp)/1000
        return float("{:.3f}".format(temp))

    def __set_threshold(self, file_name, temperature):
        temp_file_path = os.path.join(self._hwmon_path, file_name)
        try:
            with open(temp_file_path, 'w') as fd:
                fd.write(str(temperature))
            return True
        except IOError:
            return False

    def get_temperature(self):
        """
        Retrieves current temperature reading from thermal
        Returns:
            A float number of current temperature in Celsius up to nearest thousandth
            of one degree Celsius, e.g. 30.125
        """
        temp_file = "temp{}_input".format(self.ss_index)
        return self.__get_temp(temp_file)

    def get_high_threshold(self):
        """
        Retrieves the high threshold temperature of thermal
        Returns:
            A float number, the high threshold temperature of thermal in Celsius
            up to nearest thousandth of one degree Celsius, e.g. 30.125
        """
        max_crit_key = '{}_max'.format(self._airflow)
        return self._thermal_info.get(max_crit_key, None)

    def get_low_threshold(self):
        """
        Retrieves the low threshold temperature of thermal
        Returns:
            A float number, the low threshold temperature of thermal in Celsius
            up to nearest thousandth of one degree Celsius, e.g. 30.125
        """
        return 0.0

    def set_high_threshold(self, temperature):
        """
        Sets the high threshold temperature of thermal
        Args :
            temperature: A float number up to nearest thousandth of one degree Celsius,
            e.g. 30.125
        Returns:
            A boolean, True if threshold is set successfully, False if not
        """
        temp_file = "temp{}_max".format(self.ss_index)
        is_set = self.__set_threshold(temp_file, int(temperature*1000))
        file_set = False
        if is_set:
            try:
                with open(self.SS_CONFIG_PATH, 'r+') as f:
                    content = f.readlines()
                    f.seek(0)
                    ss_found = False
                    for idx, val in enumerate(content):
                        if self.name in val:
                            ss_found = True
                        elif ss_found and temp_file in val:
                            content[idx] = "    set {} {}\n".format(
                                temp_file, temperature)
                            f.writelines(content)
                            file_set = True
                            break
            except IOError:
                file_set = False

        return is_set & file_set

    def set_low_threshold(self, temperature):
        """
        Sets the low threshold temperature of thermal
        Args : 
            temperature: A float number up to nearest thousandth of one degree Celsius,
            e.g. 30.125
        Returns:
            A boolean, True if threshold is set successfully, False if not
        """
        return False

    def get_high_critical_threshold(self):
        """
        Retrieves the high critical threshold temperature of thermal
        Returns:
            A float number, the high critical threshold temperature of thermal in Celsius
            up to nearest thousandth of one degree Celsius, e.g. 30.125
        """
        max_crit_key = '{}_max_crit'.format(self._airflow)
        return self._thermal_info.get(max_crit_key, None)

    def get_low_critical_threshold(self):
        """
        Retrieves the low critical threshold temperature of thermal
        Returns:
            A float number, the low critical threshold temperature of thermal in Celsius
            up to nearest thousandth of one degree Celsius, e.g. 30.125
        """
        return 0.0

    def get_name(self):
        """
        Retrieves the name of the thermal device
            Returns:
            string: The name of the thermal device
        """
        return self._thermal_info["name"]

    def get_presence(self):
        """
        Retrieves the presence of the PSU
        Returns:
            bool: True if PSU is present, False if not
        """
        temp_file = "temp{}_input".format(self.ss_index)
        temp_file_path = os.path.join(self._hwmon_path, temp_file)
        return os.path.isfile(temp_file_path)

    def get_model(self):
        """
        Retrieves the model number (or part number) of the device
        Returns:
            string: Model/part number of device
        """
        return NULL_VAL

    def get_serial(self):
        """
        Retrieves the serial number of the device
        Returns:
            string: Serial number of device
        """
        return NULL_VAL

    def get_status(self):
        """
        Retrieves the operational status of the device
        Returns:
            A boolean value, True if device is operating properly, False if not
        """
        if not self.get_presence():
            return False

        fault_file = "temp{}_fault".format(self.ss_index)
        fault_file_path = os.path.join(self._hwmon_path, fault_file)
        if not os.path.isfile(fault_file_path):
            return True

        raw_txt = self.__read_txt_file(fault_file_path)
        return int(raw_txt) == 0
