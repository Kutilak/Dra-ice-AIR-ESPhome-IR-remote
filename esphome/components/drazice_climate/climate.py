"""Drazice Air53 - custom climate entity.

Does not duplicate any control logic - it's just a thin layer over the
existing entities (switch/select/number/button), see drazice_climate.h.
"""
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import button, climate, number, select, switch

drazice_climate_ns = cg.esphome_ns.namespace("drazice_climate")
DraziceClimate = drazice_climate_ns.class_(
    "DraziceClimate", cg.Component, climate.Climate
)

CONF_POWER_ID = "power_id"
CONF_MODE_ID = "mode_id"
CONF_TEMPERATURE_ID = "temperature_id"
CONF_SMART_OFFSET_ID = "smart_offset_id"
CONF_FAN_ID = "fan_id"
CONF_SWING_ID = "swing_id"

CONFIG_SCHEMA = climate.climate_schema(DraziceClimate).extend(cv.COMPONENT_SCHEMA).extend(
    {
        cv.Required(CONF_POWER_ID): cv.use_id(switch.Switch),
        cv.Required(CONF_MODE_ID): cv.use_id(select.Select),
        cv.Required(CONF_TEMPERATURE_ID): cv.use_id(number.Number),
        cv.Required(CONF_SMART_OFFSET_ID): cv.use_id(number.Number),
        cv.Required(CONF_FAN_ID): cv.use_id(select.Select),
        cv.Required(CONF_SWING_ID): cv.use_id(button.Button),
    }
)


async def to_code(config):
    power = await cg.get_variable(config[CONF_POWER_ID])
    mode = await cg.get_variable(config[CONF_MODE_ID])
    temperature = await cg.get_variable(config[CONF_TEMPERATURE_ID])
    smart_offset = await cg.get_variable(config[CONF_SMART_OFFSET_ID])
    fan = await cg.get_variable(config[CONF_FAN_ID])
    swing = await cg.get_variable(config[CONF_SWING_ID])

    var = await climate.new_climate(
        config, power, mode, temperature, smart_offset, fan, swing
    )
    await cg.register_component(var, config)
