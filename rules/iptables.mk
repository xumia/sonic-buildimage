# iptables package

IPTABLES_VERSION = 1.6.0+snapshot20161117
IPTABLES_VERSION_SUFFIX = 6
IPTABLES_VERSION_FULL = $(IPTABLES_VERSION)-$(IPTABLES_VERSION_SUFFIX)

IPTABLES = iptables_$(IPTABLES_VERSION_FULL)_amd64.deb
$(IPTABLES)_SRC_PATH = $(SRC_PATH)/iptables
SONIC_MAKE_DEBS += $(IPTABLES)
SONIC_STRETCH_DEBS += $(IPTABLES)

IPTABLESIP4TC = libip4tc0_$(IPTABLES_VERSION_FULL)_amd64.deb
$(eval $(call add_derived_package,$(IPTABLES),$(IPTABLESIP4TC)))

IPTABLESIP6TC = libip6tc0_$(IPTABLES_VERSION_FULL)_amd64.deb
$(eval $(call add_derived_package,$(IPTABLES),$(IPTABLESIP6TC)))

IPTABLESIPTC = libiptc0_$(IPTABLES_VERSION_FULL)_amd64.deb
$(eval $(call add_derived_package,$(IPTABLES),$(IPTABLESIPTC)))

IPXTABLES12 = libxtables12_$(IPTABLES_VERSION_FULL)_amd64.deb
$(eval $(call add_derived_package,$(IPTABLES),$(IPXTABLES12)))

# Export these variables so they can be used in a sub-make
export IPTABLES_VERSION
export IPTABLES_VERSION_FULL
export IPTABLES
