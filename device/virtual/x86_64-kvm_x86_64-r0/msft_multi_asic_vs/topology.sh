#!/bin/bash
#topolgy script for 6 ASIC PLATFORM
FIRST_FRONTEND_ASIC=0
LAST_FRONTEND_ASIC=3
FIRST_BACKEND_ASIC=4
LAST_BACKEND_ASIC=5
NUM_INTERFACES_PER_ASIC=32

start () {
    # Move external links into assigned frontend namespaces
    # eth0  - eth15: asic2 
    # eth16 - eth31: asic3 
    # eth32 - eth47: asic4
    # eth48 - eth63: asic5
    for ASIC in `seq $FIRST_FRONTEND_ASIC $LAST_FRONTEND_ASIC`; do
        for NUM in `seq 1 16`; do
            ORIG="eth$((16 * $ASIC + $NUM - 1))"
            TEMP="ethTemp999"
            NEW="eth$(($NUM + 16))"
            ip link set dev $ORIG down
            ip link set dev $ORIG name $TEMP # rename to prevent conflicts before renaming in new namespace
            ip link set dev $TEMP netns asic$ASIC
            sudo ip netns exec asic$ASIC ip link set $TEMP name $NEW # rename to final interface name
            sudo ip netns exec asic$ASIC ip link set $NEW up 
        done
    done

    # Connect all backend namespaces to frontend namespaces
    for BACKEND in `seq $FIRST_BACKEND_ASIC $LAST_BACKEND_ASIC`; do
        for FRONTEND in `seq $FIRST_FRONTEND_ASIC $LAST_FRONTEND_ASIC`; do
            for LINK in `seq 1 8`; do
                BACK_NAME="eth$((8 * $FRONTEND + $LINK))"
		FRONT_NAME="eth$((8 * $(($LAST_BACKEND_ASIC - $BACKEND)) + $LINK))" 
                TEMP_BACK="ethBack999"
                TEMP_FRONT="ethFront999"
                
                ip link add $TEMP_BACK type veth peer name $TEMP_FRONT # temporary name to prevent conflicts between interfaces
                ip link set dev $TEMP_BACK netns asic$BACKEND
                ip link set dev $TEMP_FRONT netns asic$FRONTEND 
    
                sudo ip netns exec asic$BACKEND ip link set $TEMP_BACK name $BACK_NAME
                sudo ip netns exec asic$FRONTEND ip link set $TEMP_FRONT name $FRONT_NAME

                sudo ip netns exec asic$BACKEND ip link set $BACK_NAME up
                sudo ip netns exec asic$FRONTEND ip link set $FRONT_NAME up
            done
        done
    done
}

stop() {
    for ASIC in `seq $FIRST_FRONTEND_ASIC $LAST_FRONTEND_ASIC`; do
        for NUM in `seq 1 16`; do
            TEMP="eth999"
            OLD="eth$(($NUM + 16))"
            NAME="eth$((16 * $ASIC + $NUM - 1))"
            sudo ip netns exec asic$ASIC ip link set dev $OLD down
            sudo ip netns exec asic$ASIC ip link set dev $OLD name $TEMP
            sudo ip netns exec asic$ASIC ip link set dev $TEMP netns 1
            ip link set dev $TEMP name $NAME
            ip link set dev $NAME up
        done
    done

    for ASIC in `seq $FIRST_BACKEND_ASIC $LAST_BACKEND_ASIC`; do
        for NUM in `seq 1 $NUM_INTERFACES_PER_ASIC`; do
            sudo ip netns exec asic$ASIC ip link set dev eth$NUM down
            sudo ip netns exec asic$ASIC ip link delete dev eth$NUM
        done
    done
}

case "$1" in
    start|stop)
        $1
        ;;
    *)
        echo "Usage: $0 {start|stop}"
        ;;
esac

