# FRRouting (frr) package

FRR_VERSION = 7.2.1
FRR_SUBVERSION = 0
FRR_BRANCH = frr/7.2
FRR_TAG = frr-7.2.1-s1
export FRR_VERSION FRR_SUBVERSION FRR_BRANCH FRR_TAG


FRR = frr_$(FRR_VERSION)-sonic-$(FRR_SUBVERSION)_$(CONFIGURED_ARCH).deb
$(FRR)_DEPENDS += $(LIBSNMP_DEV) $(LIBYANG_DEV)
$(FRR)_RDEPENDS += $(LIBYANG)
$(FRR)_SRC_PATH = $(SRC_PATH)/sonic-frr
SONIC_MAKE_DEBS += $(FRR)
SONIC_STRETCH_DEBS += $(FRR)

FRR_PYTHONTOOLS = frr-pythontools_$(FRR_VERSION)-sonic-$(FRR_SUBVERSION)_all.deb
$(eval $(call add_derived_package,$(FRR),$(FRR_PYTHONTOOLS)))

FRR_DBG = frr-dbgsym_$(FRR_VERSION)-sonic-$(FRR_SUBVERSION)_$(CONFIGURED_ARCH).deb
$(eval $(call add_derived_package,$(FRR),$(FRR_DBG)))

FRR_SNMP = frr-snmp_$(FRR_VERSION)-sonic-$(FRR_SUBVERSION)_$(CONFIGURED_ARCH).deb
$(eval $(call add_derived_package,$(FRR),$(FRR_SNMP)))

FRR_SNMP_DBG = frr-snmp-dbgsym_$(FRR_VERSION)-sonic-$(FRR_SUBVERSION)_$(CONFIGURED_ARCH).deb
$(eval $(call add_derived_package,$(FRR),$(FRR_SNMP_DBG)))

export FRR FRR_PYTHONTOOLS FRR_DBG FRR_SNMP FRR_SNMP_DBG

# The .c, .cpp, .h & .hpp files under src/{$DBG_SRC_ARCHIVE list}
# are archived into debug one image to facilitate debugging.
#
DBG_SRC_ARCHIVE += sonic-frr
