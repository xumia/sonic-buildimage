# swss package

SWSS = swss_1.0.0_$(CONFIGURED_ARCH).deb
$(SWSS)_SRC_PATH = $(SRC_PATH)/sonic-swss
$(SWSS)_DEPENDS += $(LIBSAIREDIS_DEV) $(LIBSAIMETADATA_DEV) $(LIBTEAM_DEV) \
    $(LIBTEAMDCTL) $(LIBTEAM_UTILS) $(LIBSWSSCOMMON_DEV) \
    $(LIBSAIVS) $(LIBSAIVS_DEV)
$(SWSS)_UNINSTALLS = $(LIBSAIVS_DEV)

$(SWSS)_RDEPENDS += $(LIBSAIREDIS) $(LIBSAIMETADATA) $(LIBTEAM) \
    $(LIBTEAMDCTL) $(LIBSWSSCOMMON) $(PYTHON3_SWSSCOMMON)
SONIC_DPKG_DEBS += $(SWSS)

SWSS_DBG = swss-dbg_1.0.0_$(CONFIGURED_ARCH).deb
$(SWSS_DBG)_DEPENDS += $(SWSS)
$(SWSS_DBG)_RDEPENDS += $(SWSS)
$(eval $(call add_derived_package,$(SWSS),$(SWSS_DBG)))

# The .c, .cpp, .h & .hpp files under src/{$DBG_SRC_ARCHIVE list}
# are archived into debug one image to facilitate debugging.
#
DBG_SRC_ARCHIVE += sonic-swss

