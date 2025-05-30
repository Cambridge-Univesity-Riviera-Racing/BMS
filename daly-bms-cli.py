#!/usr/bin/python3
import argparse
import json
import logging
import sys

from dalybms import DalyBMS
from dalybms import DalyBMSSinowealth

parser = argparse.ArgumentParser()
parser.add_argument("-d", "--device",
                    help="RS485 device, e.g. /dev/ttyUSB0",
                    type=str, required=True)
parser.add_argument("--uart", help="UART instead of RS485", action="store_true")
parser.add_argument("--sinowealth", help="BMS with Sinowealth chip", action="store_true")
parser.add_argument("--status", help="show status", action="store_true")
parser.add_argument("--soc", help="show voltage, current, SOC", action="store_true")
parser.add_argument("--mosfet", help="show mosfet status", action="store_true")
parser.add_argument("--cell-voltages", help="show cell voltages", action="store_true")
parser.add_argument("--temperatures", help="show temperature sensor values", action="store_true")
parser.add_argument("--balancing", help="show cell balancing status", action="store_true")
parser.add_argument("--errors", help="show BMS errors", action="store_true")
parser.add_argument("--all", help="show all", action="store_true")
parser.add_argument("--check", help="Nagios style check", action="store_true")
parser.add_argument("--set-charge-mosfet", help="'on' or 'off'", type=str)
parser.add_argument("--set-discharge-mosfet", help="'on' or 'off'", type=str)
parser.add_argument("--set-soc", help="'0.0' to '100.0'", type=str)
parser.add_argument("--restart", help="restart bms", action="store_true")
parser.add_argument("--retry", help="retry X times if the request fails, default 5", type=int, default=5)
parser.add_argument("--verbose", help="Verbose output", action="store_true")

parser.add_argument("--mqtt", help="Write output to MQTT", action="store_true")
parser.add_argument("--mqtt-hass", help="MQTT Home Assistant Mode", action="store_true")

parser.add_argument("--mqtt-topic",
                    help="MQTT topic to write to. default daly_bms",
                    type=str,
                    default="daly_bms")

parser.add_argument("--mqtt-broker",
                    help="MQTT broker (server). default localhost",
                    type=str,
                    default="localhost")

parser.add_argument("--mqtt-port",
                    help="MQTT port. default 1883",
                    type=int,
                    default=1883)

parser.add_argument("--mqtt-user",
                    help="Username to authenticate MQTT with",
                    type=str)

parser.add_argument("--mqtt-password",
                    help="Password to authenticate MQTT with",
                    type=str)

args = parser.parse_args()

log_format = '%(levelname)-8s [%(filename)s:%(lineno)d] %(message)s'
if args.verbose:
    level = logging.DEBUG
else:
    level = logging.WARNING

logging.basicConfig(level=level, format=log_format, datefmt='%H:%M:%S')

logger = logging.getLogger()

if args.uart:
    address = 8
else:
    address = 4

if args.sinowealth:
    bms = DalyBMSSinowealth(request_retries=args.retry, logger=logger)
else:
    bms = DalyBMS(request_retries=args.retry, address=address, logger=logger)
bms.connect(device=args.device)

result = False

mqtt_client = None
#if args.mqtt:
#    import paho.mqtt.client as paho
#
#    mqtt_client = paho.Client()
#    mqtt_client.enable_logger(logger)
#    mqtt_client.username_pw_set(args.mqtt_user, args.mqtt_password)
#    mqtt_client.connect(args.mqtt_broker, port=args.mqtt_port)


def build_mqtt_hass_config_discovery(base):
    # Instead of daly_bms should be here added a proper name (unique), like serial or something
    # At this point it can be used only one daly_bms system with hass discovery

    hass_config_topic = f'homeassistant/sensor/daly_bms/{base.replace("/", "_")}/config'
    hass_config_data = {}

    hass_config_data["unique_id"] = f'daly_bms_{base.replace("/", "_")}'
    hass_config_data["name"] = f'Daly BMS {base.replace("/", " ")}'

    if 'soc_percent' in base:
        hass_config_data["device_class"] = 'battery'
        hass_config_data["unit_of_measurement"] = '%'
    elif 'voltage' in base and not ('lowest_cell' in base or 'highest_cell' in base):
        hass_config_data["device_class"] = 'voltage'
        hass_config_data["unit_of_measurement"] = 'V'
    elif 'current' in base:
        hass_config_data["device_class"] = 'current'
        hass_config_data["unit_of_measurement"] = 'A'
    elif 'temperatures' in base:
        hass_config_data["device_class"] = 'temperature'
        hass_config_data["unit_of_measurement"] = '°C'
    elif 'capacity' in 'base':
        hass_config_data["device_class"] = 'energy'
        hass_config_data["unit_of_measurement"] = 'Ah'
    else:
        pass

    hass_config_data["json_attributes_topic"] = f'{args.mqtt_topic}{base}'
    hass_config_data["state_topic"] = f'{args.mqtt_topic}{base}'

    hass_device = {
        "identifiers": ['daly_bms'],
        "manufacturer": 'Daly',
        "model": 'Currently not available',
        "name": 'Daly BMS',
        "sw_version": 'Currently not available'
    }
    hass_config_data["device"] = hass_device

    return hass_config_topic, json.dumps(hass_config_data)


def mqtt_single_out(topic, data, retain=False):
    logger.debug(f'Send data: {data} on topic: {topic}, retain flag: {retain}')
    mqtt_client.publish(topic, data, retain=retain)


def mqtt_iterator(result, base=''):
    for key in result.keys():
        if type(result[key]) == dict:
            mqtt_iterator(result[key], f'{base}/{key}')
        else:
            if args.mqtt_hass:
                logger.debug('Sending out hass discovery message')
                topic, output = build_mqtt_hass_config_discovery(f'{base}/{key}')
                mqtt_single_out(topic, output, retain=True)

            if type(result[key]) == list:
                val = json.dumps(result[key])
            else:
                val = result[key]

            mqtt_single_out(f'{args.mqtt_topic}{base}/{key}', val)


def print_result(result):
    if args.mqtt:
        mqtt_iterator(result)
    else:
        print(json.dumps(result, indent=2))


if args.status:
    result = bms.get_status()
    print_result(result)
if args.soc:
    result = bms.get_soc()
    print_result(result)
if args.mosfet:
    result = bms.get_mosfet_status()
    print_result(result)
if args.cell_voltages:
    if not args.status:
        bms.get_status()
    result = bms.get_cell_voltages()
    print_result(result)
if args.temperatures:
    result = bms.get_temperatures()
    print_result(result)
if args.balancing:
    result = bms.get_balancing_status()
    print_result(result)
if args.errors:
    result = bms.get_errors()
    print_result(result)
if args.all:
    result = bms.get_all()
    print_result(result)

if args.check:
    status = bms.get_status()
    status_code = 0  # OK
    status_codes = ('OK', 'WARNING', 'CRITICAL', 'UNKNOWN')
    status_line = ''

    data = bms.get_soc()
    perfdata = []
    if data:
        for key, value in data.items():
            perfdata.append('%s=%s' % (key, value))

    # todo: read errors

    if status_code == 0:
        status_line = '%0.1f volt, %0.1f amper' % (data['total_voltage'], data['current'])

    print("%s - %s | %s" % (status_codes[status_code], status_line, " ".join(perfdata)))
    sys.exit(status_code)

if args.set_charge_mosfet:
    if args.set_charge_mosfet == 'on':
        on = True
    elif args.set_charge_mosfet == 'off':
        on = False
    else:
        print("invalid value '%s', expected 'on' or 'off'" % args.set_charge_mosfet)
        sys.exit(1)

    result = bms.set_charge_mosfet(on=on)

if args.set_discharge_mosfet:
    if args.set_discharge_mosfet == 'on':
        on = True
    elif args.set_discharge_mosfet == 'off':
        on = False
    else:
        print("invalid value '%s', expected 'on' or 'off'" % args.set_discharge_mosfet)
        sys.exit(1)

    result = bms.set_discharge_mosfet(on=on)

if args.set_soc:
    try :
        v = float(args.set_soc)
    except :
        print("invalid value '%s', expected float value betwen 0 and 100" % args.set_soc)
        sys.exit(1)

    result = bms.set_soc(v)

if args.restart:
    result = bms.restart()

    
if mqtt_client:
    mqtt_client.disconnect()

bms.disconnect()

if not result:
    sys.exit(1)