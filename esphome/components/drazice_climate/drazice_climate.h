// =============================================================================
// Drazice Air53 — custom ESPHome `climate` component.
//
// Introduces no new air-conditioner control logic of its own — it's a thin
// layer over the entities already defined in drazice-air53.yaml
// (switch/select/number/button) that composes them into a SINGLE
// `climate.*` entity in Home Assistant. This gives HA a native thermostat
// card (mode, temperature slider, fan speed, swing) while all the original
// entities keep working independently (Quiet, Super, Economy, Sleep,
// iFeel, timers and display backlight are untouched by this component).
//
// NOTE on "target_temperature" in Smart mode: it does not represent an
// absolute temperature there, but the relative Smart offset (−7..+7) —
// traits() switches the visible slider range depending on the current mode
// (16–30 vs −7..+7).
//
// Written against the ESPHome 2026.7.x climate API (select::Select::state
// was replaced by current_option(), returning a StringRef; custom_fan_mode
// is now a protected field set via set_custom_fan_mode_()/
// clear_custom_fan_mode_(); the list of supported custom fan modes is
// registered once on the Climate entity itself, not on ClimateTraits).
// =============================================================================
#pragma once

#include "esphome/components/climate/climate.h"
#include "esphome/components/switch/switch.h"
#include "esphome/components/number/number.h"
#include "esphome/components/select/select.h"
#include "esphome/components/button/button.h"

namespace drazice_climate {

class DraziceClimate : public esphome::Component, public esphome::climate::Climate {
 public:
  DraziceClimate(esphome::switch_::Switch *power, esphome::select::Select *mode,
                 esphome::number::Number *temperature, esphome::number::Number *smart_offset,
                 esphome::select::Select *fan, esphome::button::Button *swing)
      : power_(power),
        mode_(mode),
        temperature_(temperature),
        smart_offset_(smart_offset),
        fan_(fan),
        swing_(swing) {
    // Custom fan modes are registered once on the Climate entity (not on
    // ClimateTraits on every traits() call - that path is now deprecated
    // compat-only).
    this->set_supported_custom_fan_modes({"Medium-High", "Medium-Low"});
  }

  void setup() override { this->sync_state_from_children_(); }

  void loop() override {
    uint32_t now = millis();
    if (now - this->last_sync_ < 2000) return;
    this->last_sync_ = now;
    this->sync_state_from_children_();
  }

  esphome::climate::ClimateTraits traits() override {
    auto traits = esphome::climate::ClimateTraits();
    // No CLIMATE_SUPPORTS_CURRENT_TEMPERATURE feature flag = we can't report
    // the current temperature (no sensor) - default state, nothing to set.
    traits.set_supported_modes({
        esphome::climate::CLIMATE_MODE_OFF,
        esphome::climate::CLIMATE_MODE_HEAT,
        esphome::climate::CLIMATE_MODE_COOL,
        esphome::climate::CLIMATE_MODE_DRY,
        esphome::climate::CLIMATE_MODE_FAN_ONLY,
        esphome::climate::CLIMATE_MODE_AUTO,  // = Smart
    });

    // In Smart mode the slider represents the relative Smart offset
    // (-7..+7), otherwise the absolute temperature (16-30 C) - see note above.
    if (this->mode_->current_option() == "Smart") {
      traits.set_visual_min_temperature(-7);
      traits.set_visual_max_temperature(7);
    } else {
      traits.set_visual_min_temperature(16);
      traits.set_visual_max_temperature(30);
    }
    traits.set_visual_temperature_step(1);

    traits.set_supported_fan_modes({
        esphome::climate::CLIMATE_FAN_AUTO,
        esphome::climate::CLIMATE_FAN_HIGH,
        esphome::climate::CLIMATE_FAN_MEDIUM,
        esphome::climate::CLIMATE_FAN_LOW,
    });
    // Custom fan modes are not registered here - see constructor.

    traits.set_supported_swing_modes({
        esphome::climate::CLIMATE_SWING_OFF,
        esphome::climate::CLIMATE_SWING_VERTICAL,
    });

    return traits;
  }

  void control(const esphome::climate::ClimateCall &call) override {
    if (call.get_mode().has_value()) {
      esphome::climate::ClimateMode m = *call.get_mode();
      if (m == esphome::climate::CLIMATE_MODE_OFF) {
        this->power_->turn_off();
      } else {
        if (!this->power_->state) this->power_->turn_on();

        std::string opt = "Heat";
        if (m == esphome::climate::CLIMATE_MODE_COOL) opt = "Cool";
        else if (m == esphome::climate::CLIMATE_MODE_DRY) opt = "Dry";
        else if (m == esphome::climate::CLIMATE_MODE_FAN_ONLY) opt = "Fan Only";
        else if (m == esphome::climate::CLIMATE_MODE_HEAT) opt = "Heat";
        else if (m == esphome::climate::CLIMATE_MODE_AUTO) opt = "Smart";
        this->mode_->make_call().set_option(opt).perform();
      }
    }

    if (call.get_target_temperature().has_value()) {
      float t = *call.get_target_temperature();
      if (this->mode_->current_option() == "Smart") {
        this->smart_offset_->make_call().set_value(t).perform();
      } else {
        this->temperature_->make_call().set_value(t).perform();
      }
    }

    if (call.get_fan_mode().has_value()) {
      std::string opt = "Auto";
      switch (*call.get_fan_mode()) {
        case esphome::climate::CLIMATE_FAN_HIGH: opt = "Max"; break;
        case esphome::climate::CLIMATE_FAN_MEDIUM: opt = "Medium"; break;
        case esphome::climate::CLIMATE_FAN_LOW: opt = "Min"; break;
        default: opt = "Auto"; break;
      }
      this->fan_->make_call().set_option(opt).perform();
    } else {
      esphome::StringRef custom_fan = call.get_custom_fan_mode();
      if (!custom_fan.empty()) {
        this->fan_->make_call().set_option(custom_fan.c_str()).perform();
      }
    }

    if (call.get_swing_mode().has_value()) {
      bool want_on = (*call.get_swing_mode() != esphome::climate::CLIMATE_SWING_OFF);
      if (want_on != this->swing_assumed_on_) {
        // Swing is a stateless "toggle" pulse (see PROTOCOL.md) - there's no
        // way to read back the actual state from the unit, so we just
        // remember what we last sent.
        this->swing_->press();
        this->swing_assumed_on_ = want_on;
      }
    }

    this->sync_state_from_children_();
    this->publish_state();
  }

 protected:
  void sync_state_from_children_() {
    bool power_on = this->power_->state;
    esphome::StringRef mode_opt = this->mode_->current_option();

    this->mode = esphome::climate::CLIMATE_MODE_OFF;
    if (power_on) {
      if (mode_opt == "Cool") this->mode = esphome::climate::CLIMATE_MODE_COOL;
      else if (mode_opt == "Dry") this->mode = esphome::climate::CLIMATE_MODE_DRY;
      else if (mode_opt == "Fan Only") this->mode = esphome::climate::CLIMATE_MODE_FAN_ONLY;
      else if (mode_opt == "Heat") this->mode = esphome::climate::CLIMATE_MODE_HEAT;
      else if (mode_opt == "Smart") this->mode = esphome::climate::CLIMATE_MODE_AUTO;
    }

    bool is_smart = (mode_opt == "Smart");
    this->target_temperature = is_smart ? this->smart_offset_->state : this->temperature_->state;

    esphome::StringRef fan_opt = this->fan_->current_option();
    if (fan_opt == "Auto") {
      this->clear_custom_fan_mode_();
      this->fan_mode = esphome::climate::CLIMATE_FAN_AUTO;
    } else if (fan_opt == "Max") {
      this->clear_custom_fan_mode_();
      this->fan_mode = esphome::climate::CLIMATE_FAN_HIGH;
    } else if (fan_opt == "Medium") {
      this->clear_custom_fan_mode_();
      this->fan_mode = esphome::climate::CLIMATE_FAN_MEDIUM;
    } else if (fan_opt == "Min") {
      this->clear_custom_fan_mode_();
      this->fan_mode = esphome::climate::CLIMATE_FAN_LOW;
    } else {
      // "Medium-High" / "Medium-Low"
      this->fan_mode.reset();
      this->set_custom_fan_mode_(fan_opt);
    }

    this->swing_mode = this->swing_assumed_on_ ? esphome::climate::CLIMATE_SWING_VERTICAL
                                                : esphome::climate::CLIMATE_SWING_OFF;
  }

  esphome::switch_::Switch *power_;
  esphome::select::Select *mode_;
  esphome::number::Number *temperature_;
  esphome::number::Number *smart_offset_;
  esphome::select::Select *fan_;
  esphome::button::Button *swing_;

  bool swing_assumed_on_{false};
  uint32_t last_sync_{0};
};

}  // namespace drazice_climate
