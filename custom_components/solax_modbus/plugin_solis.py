import logging
from dataclasses import dataclass
from homeassistant.components.number import NumberEntityDescription
from homeassistant.components.select import SelectEntityDescription
from homeassistant.components.button import ButtonEntityDescription
from pymodbus.payload import BinaryPayloadBuilder, BinaryPayloadDecoder, Endian
#from .const import BaseModbusSensorEntityDescription
from custom_components.solax_modbus.const import *

_LOGGER = logging.getLogger(__name__)

""" ============================================================================================
bitmasks  definitions to characterize inverters, ogranized by group
these bitmasks are used in entitydeclarations to determine to which inverters the entity applies
within a group, the bits in an entitydeclaration will be interpreted as OR
between groups, an AND condition is applied, so all gruoups must match.
An empty group (group without active flags) evaluates to True.
example: GEN3 | GEN4 | X1 | X3 | EPS 
means:  any inverter of tyoe (GEN3 or GEN4) and (X1 or X3) and (EPS)
An entity can be declared multiple times (with different bitmasks) if the parameters are different for each inverter type
"""

####
#
# Placeholder for now
#
####

GEN            = 0x0001 # base generation for MIC, PV, AC
GEN2           = 0x0002
GEN3           = 0x0004
GEN4           = 0x0008
ALL_GEN_GROUP  = GEN2 | GEN3 | GEN4 | GEN

X1             = 0x0100
X3             = 0x0200
ALL_X_GROUP    = X1 | X3

PV             = 0x0400 # Needs further work on PV Only Inverters
AC             = 0x0800
HYBRID         = 0x1000
MIC            = 0x2000
ALL_TYPE_GROUP = PV | AC | HYBRID | MIC

EPS            = 0x8000
ALL_EPS_GROUP  = EPS

DCB            = 0x10000 # dry contact box - gen4
ALL_DCB_GROUP  = DCB


ALLDEFAULT = 0 # should be equivalent to HYBRID | AC | GEN2 | GEN3 | GEN4 | X1 | X3 


def matchInverterWithMask (inverterspec, entitymask, serialnumber = 'not relevant', blacklist = None):
    # returns true if the entity needs to be created for an inverter
    genmatch = ((inverterspec & entitymask & ALL_GEN_GROUP)  != 0) or (entitymask & ALL_GEN_GROUP  == 0)
    xmatch   = ((inverterspec & entitymask & ALL_X_GROUP)    != 0) or (entitymask & ALL_X_GROUP    == 0)
    hybmatch = ((inverterspec & entitymask & ALL_TYPE_GROUP) != 0) or (entitymask & ALL_TYPE_GROUP == 0)
    epsmatch = ((inverterspec & entitymask & ALL_EPS_GROUP)  != 0) or (entitymask & ALL_EPS_GROUP  == 0)
    dcbmatch = ((inverterspec & entitymask & ALL_DCB_GROUP)  != 0) or (entitymask & ALL_DCB_GROUP  == 0)
    blacklisted = False
    if blacklist:
        for start in blacklist: 
            if serialnumber.startswith(start) : blacklisted = True
    return (genmatch and xmatch and hybmatch and epsmatch and dcbmatch) and not blacklisted

# ======================= end of bitmask handling code =============================================

# ====================== find inverter type and details ===========================================

def _read_serialnr(hub, address, swapbytes):
    res = None
    try:
        inverter_data = hub.read_input_registers(unit=hub._modbus_addr, address=address, count=8)
        if not inverter_data.isError(): 
            decoder = BinaryPayloadDecoder.fromRegisters(inverter_data.registers, byteorder=Endian.Big)
            res = decoder.decode_string(14).decode("ascii")
            if swapbytes: 
                ba = bytearray(res,"ascii") # convert to bytearray for swapping
                ba[0::2], ba[1::2] = ba[1::2], ba[0::2] # swap bytes ourselves - due to bug in Endian.Little ?
                res = str(ba, "ascii") # convert back to string
            hub.seriesnumber = res    
    except Exception as ex: _LOGGER.warning(f"{hub.name}: attempt to read serialnumber failed at 0x{address:x}", exc_info=True)
    if not res: _LOGGER.warning(f"{hub.name}: reading serial number from address 0x{address:x} failed; other address may succeed")
    _LOGGER.info(f"Read {hub.name} 0x{address:x} serial number: {res}, swapped: {swapbytes}")
    #return 'SP1ES2' 
    return res

def determineInverterType(hub, configdict):
    _LOGGER.info(f"{hub.name}: trying to determine inverter type")
    seriesnumber                       = _read_serialnr(hub, 33004,  swapbytes = False)
    if not seriesnumber: 
        _LOGGER.error(f"{hub.name}: cannot find serial number, even not for other Inverter")
        seriesnumber = "unknown"

    # derive invertertype from seriiesnumber
    if   seriesnumber.startswith('303105'):  invertertype = HYBRID | X1 # Hybrid Gen5 3kW
    elif seriesnumber.startswith('363105'):  invertertype = HYBRID | X1 # Hybrid Gen5 3.6kW
    elif seriesnumber.startswith('463105'):  invertertype = HYBRID | X1 # Hybrid Gen5 4.6kW
    elif seriesnumber.startswith('503105'):  invertertype = HYBRID | X1 # Hybrid Gen5 5kW
    elif seriesnumber.startswith('603105'):  invertertype = HYBRID | X1 # Hybrid Gen5 6kW
    #elif seriesnumber.startswith('SD1'):  invertertype = PV | X3 # Older Probably 3phase
    #elif seriesnumber.startswith('SF4'):  invertertype = PV | X3 # Older Probably 3phase
    #elif seriesnumber.startswith('SH1'):  invertertype = PV | X3 # Older Probably 3phase
    #elif seriesnumber.startswith('SL1'):  invertertype = PV | X3 # Older Probably 3phase
    #elif seriesnumber.startswith('SJ2'):  invertertype = PV | X3 # Older Probably 3phase

    else: 
        invertertype = 0
        _LOGGER.error(f"unrecognized {hub.name} inverter type - serial number : {seriesnumber}")
    read_eps = configdict.get(CONF_READ_EPS, DEFAULT_READ_EPS)
    read_dcb = configdict.get(CONF_READ_DCB, DEFAULT_READ_DCB)
    if read_eps: invertertype = invertertype | EPS 
    if read_dcb: invertertype = invertertype | DCB
    hub.invertertype = invertertype


@dataclass
class SolisModbusButtonEntityDescription(BaseModbusButtonEntityDescription):
    allowedtypes: int = ALLDEFAULT # maybe 0x0000 (nothing) is a better default choice

@dataclass
class SolisModbusNumberEntityDescription(BaseModbusNumberEntityDescription):
    allowedtypes: int = ALLDEFAULT # maybe 0x0000 (nothing) is a better default choice

@dataclass
class SolisModbusSelectEntityDescription(BaseModbusSelectEntityDescription):
    allowedtypes: int = ALLDEFAULT # maybe 0x0000 (nothing) is a better default choice


# This section needs more work to be like plugin_Solis
@dataclass
class SolisModbusSensorEntityDescription(BaseModbusSensorEntityDescription):
    """A class that describes Solis Modbus sensor entities."""
    order16: int = Endian.Big
    order32: int = Endian.Big
    unit: int = REGISTER_U16
    register_type: int= REG_HOLDING



BUTTON_TYPES = []

NUMBER_TYPES = [
    SolisModbusNumberEntityDescription( name = "Timed Charge End Hours",
        key = "timed_charge_end_h", 
        register = 43145,
        fmt = "i",
        native_min_value = 0,
        native_max_value = 23,
        native_step = 1,
        native_unit_of_measurement = TIME_HOURS,
        allowedtypes = HYBRID,
        entity_category = EntityCategory.CONFIG,
        icon="mdi:battery-clock",
    ),
    SolisModbusNumberEntityDescription( name = "Timed Charge End Minutes",
        key = "timed_charge_end_m",
        register = 43146,
        fmt = "i",
        native_min_value = 0,
        native_max_value = 59,
        native_step = 1,
        native_unit_of_measurement = TIME_MINUTES,
        allowedtypes = HYBRID,
        entity_category = EntityCategory.CONFIG,
        icon="mdi:battery-clock",
    ),
    SolisModbusNumberEntityDescription( name = "Timed Charge Start Hours",
        key = "timed_charge_start_h", 
        register = 43143,
        fmt = "i",
        native_min_value = 0,
        native_max_value = 23,
        native_step = 1,
        native_unit_of_measurement = TIME_HOURS,
        allowedtypes =HYBRID,
        entity_category = EntityCategory.CONFIG,
        icon="mdi:battery-clock",
    ),
    SolisModbusNumberEntityDescription( name = "Timed Charge Start Minutes",
        key = "timed_charge_start_m",
        register = 43144,
        fmt = "i",
        native_min_value = 0,
        native_max_value = 59,
        native_step = 1,
        native_unit_of_measurement = TIME_MINUTES,
        allowedtypes = HYBRID,
        entity_category = EntityCategory.CONFIG,
        icon="mdi:battery-clock",
    ),
    SolisModbusNumberEntityDescription( name = "Timed Discharge End Hours",
        key = "timed_discharge_end_h", 
        register = 43149,
        fmt = "i",
        native_min_value = 0,
        native_max_value = 23,
        native_step = 1,
        native_unit_of_measurement = TIME_HOURS,
        allowedtypes = HYBRID,
        entity_category = EntityCategory.CONFIG,
        icon="mdi:battery-clock",
    ),
    SolisModbusNumberEntityDescription( name = "Timed Discharge End Minutes",
        key = "timed_discharge_end_m",
        register = 43150,
        fmt = "i",
        native_min_value = 0,
        native_max_value = 59,
        native_step = 1,
        native_unit_of_measurement = TIME_MINUTES,
        allowedtypes = HYBRID,
        entity_category = EntityCategory.CONFIG,
        icon="mdi:battery-clock",
    ),
    SolisModbusNumberEntityDescription( name = "Timed Discharge Start Hours",
        key = "timed_discharge_start_h", 
        register = 43147,
        fmt = "i",
        native_min_value = 0,
        native_max_value = 23,
        native_step = 1,
        native_unit_of_measurement = TIME_HOURS,
        allowedtypes =HYBRID,
        entity_category = EntityCategory.CONFIG,
        icon="mdi:battery-clock",
    ),
    SolisModbusNumberEntityDescription( name = "Timed Discharge Start Minutes",
        key = "timed_discharge_start_m",
        register = 43148,
        fmt = "i",
        native_min_value = 0,
        native_max_value = 59,
        native_step = 1,
        native_unit_of_measurement = TIME_MINUTES,
        allowedtypes = HYBRID,
        entity_category = EntityCategory.CONFIG,
        icon="mdi:battery-clock",
    ),
]

SELECT_TYPES = []

SENSOR_TYPES: list[SolisModbusSensorEntityDescription] = [ 

###
#
# Input Registers
#
###

    SolisModbusSensorEntityDescription(
        name="Serial Number",
        key="serialnumber",
        register=33004,
        register_type=REG_INPUT,
        unit=REGISTER_STR,
        wordcount=8,
        entity_registry_enabled_default=False,
        allowedtypes= HYBRID,
        entity_category = EntityCategory.DIAGNOSTIC,
        icon="mdi:information",
    ),
    SolisModbusSensorEntityDescription(
        name="RTC",
        key="rtc",
        register = 33023,
        register_type = REG_INPUT,
        unit = REGISTER_WORDS,
        wordcount = 6,
        scale = value_function_rtc,
        entity_registry_enabled_default=False,
        allowedtypes= HYBRID,
        entity_category = EntityCategory.DIAGNOSTIC,
        icon="mdi:clock",
    ),
    SolisModbusSensorEntityDescription(
        name="Power Generation Total",
        key="power_generation_total",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        icon="mdi:solar-power",
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
        register = 33029,
        register_type = REG_INPUT,
        unit = REGISTER_U32,
        allowedtypes= HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name="Power Generation This Month",
        key="power_generation_this_month",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        icon="mdi:solar-power",
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
        register = 33031,
        register_type = REG_INPUT,
        unit = REGISTER_U32,
        allowedtypes= HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name="Power Generation Last Month",
        key="power_generation_last_month",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        icon="mdi:solar-power",
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
        register = 33033,
        register_type = REG_INPUT,
        unit = REGISTER_U32,
        allowedtypes= HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name="Power Generation Today",
        key="power_generation_today",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        icon="mdi:solar-power",
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
        register = 33035,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        allowedtypes= HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name="Power Generation Yesterday",
        key="power_generation_yesterday",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        icon="mdi:solar-power",
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
        register = 33036,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        allowedtypes= HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name="Power Generation This Year",
        key="power_generation_this_year",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        icon="mdi:solar-power",
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
        register = 33037,
        register_type = REG_INPUT,
        unit = REGISTER_U32,
        allowedtypes= HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name="Power Generation Last Year",
        key="power_generation_last_year",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        icon="mdi:solar-power",
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
        register = 33039,
        register_type = REG_INPUT,
        unit = REGISTER_U32,
        allowedtypes= HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name="PV Voltage 1",
        key="pv_voltage_1",
        native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
        device_class=DEVICE_CLASS_VOLTAGE,
        register = 33049,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        allowedtypes= HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name="PV Current 1",
        key="pv_current_1",
        native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
        device_class=DEVICE_CLASS_CURRENT,
        register = 33050,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        allowedtypes= HYBRID,
        icon="mdi:current-dc",
    ),
    SolisModbusSensorEntityDescription(
        name="PV Voltage 2",
        key="pv_voltage_2",
        native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
        device_class=DEVICE_CLASS_VOLTAGE,
        register = 33051,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        allowedtypes= HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name="PV Current 2",
        key="pv_current_2",
        native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
        device_class=DEVICE_CLASS_CURRENT,
        register = 33052,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        allowedtypes= HYBRID,
        icon="mdi:current-dc",
    ),
    SolisModbusSensorEntityDescription(
        name="PV Voltage 3",
        key="pv_voltage_3",
        native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
        device_class=DEVICE_CLASS_VOLTAGE,
        register = 33053,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        entity_registry_enabled_default=False,
        allowedtypes= HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name="PV Current 3",
        key="pv_current_3",
        native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
        device_class=DEVICE_CLASS_CURRENT,
        register = 33054,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        entity_registry_enabled_default=False,
        allowedtypes= HYBRID,
        icon="mdi:current-dc",
    ),
    SolisModbusSensorEntityDescription(
        name="PV Voltage 4",
        key="pv_voltage_4",
        native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
        device_class=DEVICE_CLASS_VOLTAGE,
        register = 33055,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        entity_registry_enabled_default=False,
        allowedtypes= HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name="PV Current 4",
        key="pv_current_4",
        native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
        device_class=DEVICE_CLASS_CURRENT,
        register = 33056,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        entity_registry_enabled_default=False,
        allowedtypes= HYBRID,
        icon="mdi:current-dc",
    ),
    SolisModbusSensorEntityDescription(
        name="PV Total Power",
        key="pv_total_power",
        native_unit_of_measurement=POWER_WATT,
        device_class=DEVICE_CLASS_POWER,
        state_class=STATE_CLASS_MEASUREMENT,
        register = 33057,
        register_type = REG_INPUT,
        unit = REGISTER_U32,
        allowedtypes= HYBRID,
        icon="mdi:solar-power-variant",
    ),
    SolisModbusSensorEntityDescription(
        name="Inverter Voltage",
        key="inverter_voltage",
        native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
        device_class=DEVICE_CLASS_VOLTAGE,
        register = 33073,
        scale = 0.1,
        register_type = REG_INPUT,
        rounding = 1,
        allowedtypes= HYBRID | X1,
    ),
    SolisModbusSensorEntityDescription(
        name="Inverter Voltage R",
        key="grid_voltage_r",
        native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
        device_class=DEVICE_CLASS_VOLTAGE,
        register = 33073,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        allowedtypes = HYBRID | X3,
    ),
    SolisModbusSensorEntityDescription(
        name="Inverter Voltage S",
        key="grid_voltage_s",
        native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
        device_class=DEVICE_CLASS_VOLTAGE,
        register = 33074,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        allowedtypes = HYBRID | X3,
    ),
    SolisModbusSensorEntityDescription(
        name="Inverter Voltage T",
        key="grid_voltage_t",
        native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
        device_class=DEVICE_CLASS_VOLTAGE,
        register = 33075,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        allowedtypes = HYBRID | X3,
    ),
    SolisModbusSensorEntityDescription(
        name="Inverter Current",
        key="inverter_current",
        native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
        device_class=DEVICE_CLASS_CURRENT,
        register = 33076,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        allowedtypes= HYBRID | X1,
    ),
    SolisModbusSensorEntityDescription(
        name="Inverter Current R",
        key="grid_current_r",
        native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
        device_class=DEVICE_CLASS_CURRENT,
        register = 33076,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        allowedtypes = HYBRID | X3,
    ),
    SolisModbusSensorEntityDescription(
        name="Inverter Current S",
        key="grid_current_s",
        native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
        device_class=DEVICE_CLASS_CURRENT,
        register = 33077,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        allowedtypes = HYBRID | X3,
    ),
    SolisModbusSensorEntityDescription(
        name="Inverter Current T",
        key="grid_current_t",
        native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
        device_class=DEVICE_CLASS_CURRENT,
        register = 33078,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        allowedtypes = HYBRID | X3,
    ),
    SolisModbusSensorEntityDescription(
        name = "ActivePower",
        key = "activepower",
        native_unit_of_measurement = ENERGY_KILO_WATT_HOUR,
        device_class = DEVICE_CLASS_ENERGY,
        register = 33079,
        register_type = REG_INPUT,
        unit = REGISTER_S32,
        allowedtypes = HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name = "ReactivePower",
        key = "reactivepower",
        native_unit_of_measurement = ENERGY_KILO_WATT_HOUR,
        device_class = DEVICE_CLASS_ENERGY,
        register = 33081,
        register_type = REG_INPUT,
        unit = REGISTER_S32,
        allowedtypes = HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name = "ApparentPower",
        key = "apparentpower",
        native_unit_of_measurement=POWER_VOLT_AMPERE,
        device_class = DEVICE_CLASS_POWER,
        register = 33083,
        register_type = REG_INPUT,
        unit = REGISTER_S32,
        allowedtypes = HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name="Inverter Temperature",
        key="inverter_temperature",
        native_unit_of_measurement=TEMP_CELSIUS,
        device_class=DEVICE_CLASS_TEMPERATURE,
        state_class=STATE_CLASS_MEASUREMENT,
        register = 33093,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        allowedtypes = HYBRID,
        entity_category = EntityCategory.DIAGNOSTIC,
    ),
    SolisModbusSensorEntityDescription(
        name="Inverter Frequency",
        key="grid_frequency",
        native_unit_of_measurement=FREQUENCY_HERTZ,
        device_class=DEVICE_CLASS_FREQUENCY,
        register = 33094,
        register_type = REG_INPUT,
        scale = 0.01,
        rounding = 2,
        allowedtypes = HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name = "Meter Total ActivePower",
        key = "meter_total_activepower",
        native_unit_of_measurement = ENERGY_KILO_WATT_HOUR,
        device_class = DEVICE_CLASS_ENERGY,
        register = 33126,
        register_type = REG_INPUT,
        unit = REGISTER_U32,
        allowedtypes = HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name="Meter Voltage",
        key="meter_voltage",
        native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
        device_class=DEVICE_CLASS_VOLTAGE,
        register = 330128,
        register_type = REG_INPUT,
        allowedtypes = HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name="Meter Current",
        key="meter_current",
        native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
        device_class=DEVICE_CLASS_CURRENT,
        register = 33129,
        register_type = REG_INPUT,
        allowedtypes= HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name = "Meter ActivePower",
        key = "meter_activepower",
        native_unit_of_measurement = ENERGY_KILO_WATT_HOUR,
        device_class = DEVICE_CLASS_ENERGY,
        register = 33130,
        register_type = REG_INPUT,
        unit = REGISTER_S32,
        allowedtypes = HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name = "Battery Voltage",
        key = "battery_voltage",
        native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT,
        device_class = DEVICE_CLASS_VOLTAGE,
        register = 33133,
        #newblock = True,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        allowedtypes = HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name = "Battery Current",
        key = "battery_current",
        native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
        device_class=DEVICE_CLASS_CURRENT,
        register = 33134,
        register_type = REG_INPUT,
        unit = REGISTER_S16,
        scale = 0.1,
        rounding = 1,
        allowedtypes = HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name="Battery SOC",
        key="battery_soc",
        native_unit_of_measurement=PERCENTAGE,
        device_class=DEVICE_CLASS_BATTERY,
        register = 33139,
        register_type = REG_INPUT,
        allowedtypes = HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name="Battery SOH",
        key="battery_soh",
        native_unit_of_measurement=PERCENTAGE,
        register = 33140,
        register_type = REG_INPUT,
        allowedtypes = HYBRID,
        icon="mdi:battery-heart",
        entity_category = EntityCategory.DIAGNOSTIC,
    ),
    SolisModbusSensorEntityDescription(
        name = "BMS Battery Voltage",
        key = "bms_battery_voltage",
        native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT,
        device_class = DEVICE_CLASS_VOLTAGE,
        register = 33141,
        #newblock = True,
        register_type = REG_INPUT,
        scale = 0.01,
        rounding = 2,
        allowedtypes = HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name = "BMS Battery Current",
        key = "bms_battery_current",
        native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
        device_class=DEVICE_CLASS_CURRENT,
        register = 33142,
        register_type = REG_INPUT,
        unit = REGISTER_S16,
        scale = 0.01,
        rounding = 2,
        allowedtypes = HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name = "BMS Battery Charge Limit",
        key = "bms_battery_charge_limit",
        native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
        device_class=DEVICE_CLASS_CURRENT,
        register = 33143,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        allowedtypes = HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name = "BMS Battery Discharge Limit",
        key = "bms_battery_discharge_limit",
        native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
        device_class=DEVICE_CLASS_CURRENT,
        register = 33144,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        allowedtypes = HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name="House Load",
        key="house_load",
        native_unit_of_measurement=POWER_WATT,
        device_class=DEVICE_CLASS_POWER,
        state_class=STATE_CLASS_MEASUREMENT,
        register = 33147,
        register_type = REG_INPUT,
        allowedtypes = HYBRID,
        icon="mdi:home",
    ), 
    SolisModbusSensorEntityDescription(
        name="Bypass Load",
        key="bypass_load",
        native_unit_of_measurement=POWER_WATT,
        device_class=DEVICE_CLASS_POWER,
        state_class=STATE_CLASS_MEASUREMENT,
        register = 33148,
        register_type = REG_INPUT,
        allowedtypes = HYBRID,
        icon="mdi:home",
    ),
    SolisModbusSensorEntityDescription(
        name="Battery Power",
        key="battery_power",
        native_unit_of_measurement=POWER_WATT,
        device_class=DEVICE_CLASS_POWER,
        state_class=STATE_CLASS_MEASUREMENT,
        register = 33149,
        register_type = REG_INPUT,
        unit = REGISTER_S32,
        allowedtypes = HYBRID,
        icon="mdi:home",
    ),
    SolisModbusSensorEntityDescription(
        name = "Total Battery Charge",
        key = "total_battery_charge",
        native_unit_of_measurement = ENERGY_KILO_WATT_HOUR,
        device_class = DEVICE_CLASS_ENERGY,
        register = 33161,
        register_type = REG_INPUT,
        unit = REGISTER_U32,
        allowedtypes = HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name = "Battery Charge Today",
        key = "battery_charge_today",
        native_unit_of_measurement = ENERGY_KILO_WATT_HOUR,
        device_class = DEVICE_CLASS_ENERGY,
        register = 33163,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        allowedtypes = HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name = "Battery Charge Yesterday",
        key = "battery_charge_yesterday",
        native_unit_of_measurement = ENERGY_KILO_WATT_HOUR,
        device_class = DEVICE_CLASS_ENERGY,
        register = 33164,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        allowedtypes = HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name = "Total Battery Discharge",
        key = "total_battery_discharge",
        native_unit_of_measurement = ENERGY_KILO_WATT_HOUR,
        device_class = DEVICE_CLASS_ENERGY,
        register = 33165,
        register_type = REG_INPUT,
        unit = REGISTER_U32,
        allowedtypes = HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name = "Battery Discharge Today",
        key = "battery_discharge_today",
        native_unit_of_measurement = ENERGY_KILO_WATT_HOUR,
        device_class = DEVICE_CLASS_ENERGY,
        register = 33167,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        allowedtypes = HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name = "Battery Discharge Yesterday",
        key = "battery_discharge_yesterday",
        native_unit_of_measurement = ENERGY_KILO_WATT_HOUR,
        device_class = DEVICE_CLASS_ENERGY,
        register = 33168,
        register_type = REG_INPUT,
        scale = 0.1,
        rounding = 1,
        allowedtypes = HYBRID,
    ),
    SolisModbusSensorEntityDescription(
        name="Grid Import Total",
        key="grid_import_total",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
        register = 33169,
        register_type = REG_INPUT,
        unit = REGISTER_U32,
        entity_registry_enabled_default=False,
        allowedtypes= HYBRID,
        icon="mdi:home-import-outline",
    ),
    SolisModbusSensorEntityDescription(
        name="Grid Import Today",
        key="grid_import_today",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
        register = 33171,
        register_type = REG_INPUT,
        entity_registry_enabled_default=False,
        allowedtypes= HYBRID,
        icon="mdi:home-import-outline",
    ),
    SolisModbusSensorEntityDescription(
        name="Grid Import Yesterday",
        key="grid_import_yesterday",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
        register = 33172,
        register_type = REG_INPUT,
        entity_registry_enabled_default=False,
        allowedtypes= HYBRID,
        icon="mdi:home-import-outline",
    ),
    SolisModbusSensorEntityDescription(
        name="Grid Export Total",
        key="grid_export_total",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
        register = 33173,
        register_type = REG_INPUT,
        unit = REGISTER_U32,
        entity_registry_enabled_default=False,
        allowedtypes= HYBRID,
        icon="mdi:home-import-outline",
    ),
    SolisModbusSensorEntityDescription(
        name="Grid Export Today",
        key="grid_export_today",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
        register = 33175,
        register_type = REG_INPUT,
        entity_registry_enabled_default=False,
        allowedtypes= HYBRID,
        icon="mdi:home-import-outline",
    ),
    SolisModbusSensorEntityDescription(
        name="Grid Export Yesterday",
        key="grid_export_yesterday",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
        register = 33176,
        register_type = REG_INPUT,
        entity_registry_enabled_default=False,
        allowedtypes= HYBRID,
        icon="mdi:home-import-outline",
    ),
    SolisModbusSensorEntityDescription(
        name="House Load Total",
        key="house_load_total",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
        register = 33177,
        register_type = REG_INPUT,
        unit = REGISTER_U32,
        allowedtypes = HYBRID,
        icon="mdi:home",
    ),
    SolisModbusSensorEntityDescription(
        name="House Load Today",
        key="house_load_today",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
        register = 33179,
        register_type = REG_INPUT,
        allowedtypes = HYBRID,
        icon="mdi:home",
    ),
    SolisModbusSensorEntityDescription(
        name="House Load Yesterday",
        key="house_load_yesterday",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
        register = 33180,
        register_type = REG_INPUT,
        allowedtypes = HYBRID,
        icon="mdi:home",
    ),
]