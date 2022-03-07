#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 
# flower-power - Read the history file of the Parrot Flower Power
# 
# Copyright (C) 2022 Sony Computer Science Laboratories
# Authors: Doug Boari, P. Hanappe
# 
# This file is part of the ROMI tools.
# 
# flower-power is free software: you can redistribute it
# and/or modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# 
# flower-power is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
# 
# You should have received a copy of the GNU Lesser General Public
# License along with plantdb.  If not, see <https://www.gnu.org/licenses/>.
# ------------------------------------------------------------------------------

# This file uses code from:
# https://github.com/Parrot-Developers/node-flower-power/blob/master/index.js
# In particular, in the three function convert_temperature(), convert_soil_moisture(),
# and convert_sunlight()
# The original code is available under the MIT License

# This code relied uses the documentation provided in the Readme of this project:
# https://github.com/BuBuaBu/flower-power-history/blob/master/index.js
# In particular, the documentation detailed the memory layout of the binary
# hostory file.

import math
import time
from datetime import datetime
from abc import ABC, abstractmethod
import struct
import threading
import json
import argparse
import gatt

    
def _little_endian(data, signed=False):
    return int.from_bytes(data, byteorder='little', signed=signed)

def _get_buffer_index(data):
    return _little_endian(data[0:2])

def _get_length(data):
    return _little_endian(data[2:6])

def _get_payload(data):
    return data[2:]

def convert_temperature(raw):
    value = (0.00000003044 * math.pow(raw, 3.0)
             - 0.00008038 * math.pow(raw, 2.0)
             + 0.1149 * raw 
             - 30.449999999999999)
    if value < -10.0:
        value = -10.0
    elif value > 55.0:
        value = 55.0
    return value
    

def convert_soil_moisture(raw):
    soil_moisture = (0.0000000010698 * math.pow(raw, 4.0)
                     - 0.00000152538 * math.pow(raw, 3.0)
                     + 0.000866976 * math.pow(raw, 2.0)
                     - 0.169422 * raw
                     + 11.4293)

    soil_moisture = 100.0 * (0.0000045 * math.pow(soil_moisture, 3.0)
                             - 0.00055 * math.pow(soil_moisture, 2.0)
                             + 0.0292 * soil_moisture
                             - 0.053)
    return soil_moisture

def convert_sunlight(raw):
    return 0.08640000000000001 * (192773.17000000001 * math.pow(raw, -1.0606619))



class HistoryFile():
    def __init__(self):
        self._current_time = 0
        self._device_time = 0
        self._session_id = 0
        self._measurement_period = 0
        self._session_start_index = 0
        self._first_entry_index = 0
        self._last_entry_index = 0
        self._last_entry_time = 0
        self._number_entries = 0
        self._length = 0
        self._count = 0
        self._bytes_downloaded = 0
        self._buffers = {}
        self._data = bytearray()
        self._records = []

    def append(self, index, data):
        self._buffers[index] = data
        
    def store(self, path):
        self._assemble()
        self._convert()
        self._store(path)

    def _assemble(self):
        for i in range(1, self._count):
            buf = self._buffers[i]
            payload = _get_payload(buf)
            n = 18
            if len(self._data) + n > self._length:
                n = self._length - len(self._data)
            self._data += payload[:n]
        
    def _convert(self):
        self._convert_header()
        self._convert_records()

    @property
    def _startup_time(self):
        return self._current_time - self._device_time	
        
    def _convert_header(self):
        header = self._data[:16]
        (dummy, num_entries, last_entry_time, first_entry_index,
         last_entry_index, session_id, period) = struct.unpack(">HHIHHHH", header)
        #print(f"last_entry_time {last_entry_time}")
        #print(f"first_entry_index {first_entry_index}")
        #print(f"last_entry_index {last_entry_index}")
        self._last_entry_time = last_entry_time
        #self._first_entry_index = first_entry_index
        
    def _convert_records(self):
        for i in range(self._number_entries):
            offset = 16 + i * 12
            frame = self._data[offset:offset+12]
            self._convert_record(frame, self._first_entry_index + i)
        
    def _convert_record(self, frame, index):
        if len(frame) != 12:
            return
        (air_temp, light, soil_ec, soil_temp, soil_vwc, battery) = struct.unpack(">HHHHHH", frame)

        timestamp = self._record_timestamp(index)
        air_temperature = convert_temperature(air_temp)
        soil_temperature = convert_temperature(soil_temp)
        soil_moisture = convert_soil_moisture(soil_vwc)
        sunlight = convert_sunlight(light)
        
        self._records.append({
            'index': index,
            'date': str(datetime.fromtimestamp(timestamp)),
            'timestamp': timestamp,
            'air-temperature': air_temperature,
            'soil-temperature': soil_temperature,
            'soil-moisture': soil_moisture,
            'sunlight': sunlight,
            'raw-values': {
                'air-temperature': air_temp,
                'soil-temperature': soil_temp,
                'soil-moisture': soil_vwc,
                'sunlight': light
            }
        })
        
    def _record_timestamp(self, index):
        return self._startup_time + self._record_relative_timestamp(index)	
        
    def _record_relative_timestamp(self, index):
        return (self._last_entry_time
                - (self._last_entry_index - index) * self._measurement_period)	
        
    def _store(self, path):
        data = {
            'first-entry-index': self._first_entry_index,
            'last-entry-index': self._last_entry_index,
            'session-start-index': self._session_start_index,
            'period': self._measurement_period,
            'session-id': self._session_id,
            'measurements': self._records
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=4)
            
class StateTransitionHandler(ABC):
    def __init__(self):
        pass

    def do_transition(self, state_machine, device, history, data=None):
        pass

#########################################################################
# State transitions
    
class DoBoth(StateTransitionHandler):
    def __init__(self, first, second):
        self._first = first
        self._second = second

    def do_transition(self, state_machine, device, history, data=None):
        self._first.do_transition(state_machine, device, history, data)
        self._second.do_transition(state_machine, device, history, data)

        
class TurnLedOn(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        device.write_byte(device.led, 1)

class TurnLedOff(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        device.write_byte(device.led, 0)

class RequestTxStatus(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        device.read(device.tx_status)

class CheckTxStatusDuringInit(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        status = data[0]
        if status == FlowerPower.TX_IDLE:
            state_machine.handle_event(DownloadStateMachine.EVENT_TX_STATUS_IDLE)
        else:
            state_machine.handle_event(DownloadStateMachine.EVENT_TX_STATUS_NOT_IDLE)
            
class CheckTxStatusDuringTransfer(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        status = data[0]
        if status == FlowerPower.TX_AWAITING_ACK:
            #print(f"CheckTxStatusDuringTransfer: TX Status switched to ACK")
            state_machine.handle_event(DownloadStateMachine.EVENT_TX_STATUS_WAITING_ACK)
        elif status == FlowerPower.TX_TRANSFERRING:
            #print(f"CheckTxStatusDuringTransfer: TX Status switched to Tranferring")
            state_machine.handle_event(DownloadStateMachine.EVENT_TX_STATUS_TRANSFERRING)
        elif status == FlowerPower.TX_IDLE:
            #print(f"CheckTxStatusDuringTransfer: TX Status switched to Idle")
            state_machine.handle_event(DownloadStateMachine.EVENT_TX_STATUS_IDLE)
        else:
            print(f"CheckTxStatusDuringTransfer: Got unexpected status {status}")
            
class CancelTransfer(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        device.write_byte(device.rx_status, FlowerPower.RX_CANCEL)

class SendTxStatusAck(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        #print(f"SendTxStatusAck: Writing ACK to RX Status")
        device.write_byte(device.rx_status, FlowerPower.RX_ACK)
    
class RequestTime(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        device.read(device.clock)

class InitializeTime(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        history._current_time = int(time.time())
        history._device_time = _little_endian(data)
        
class RequestSessionID(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        device.read(device.session_id)

class InitializeSessionID(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        history._session_id = _little_endian(data)

class RequestMeasurementPeriod(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        device.read(device.measurement_period)

class InitializeMeasurementPeriod(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        history._measurement_period = _little_endian(data)

class RequestSessionStartIndex(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        device.read(device.session_start_index)

class InitializeSessionStartIndex(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        history._session_start_index = _little_endian(data)

class RequestLastEntryIndex(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        device.read(device.last_entry_index)

class InitializeLastEntryIndex(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        history._last_entry_index = _little_endian(data)

class RequestNumberOfEntries(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        device.read(device.number_entries)

class InitializeNumberOfEntries(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        history._number_entries = _little_endian(data)

class RegisterForTxBufferNotifications(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        device.register_notifications(device.tx_buffer)

class RegisterForTxStatusNotifications(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        device.register_notifications(device.tx_status)

class WriteTransferStartIndex(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        history._first_entry_index = history._last_entry_index - history._number_entries + 1
        print(f"last index {history._last_entry_index}, "
              + f"#entries {history._number_entries}, "
                  + f"#first_entry_index {history._first_entry_index}")
        device.write_u32(device.transfer_start_index, history._first_entry_index)


class StartReceiving(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        device.write_byte(device.rx_status, FlowerPower.RX_RECEIVING) 

class PrepareForFirstBuffer(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        pass

class HandleFirstBuffer(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        history._count = 1
        history._bytes_downloaded = 0
        index = _get_buffer_index(data)
        history._length = _get_length(data)
        history.append(index, data)
        print('.', end='')

class HandleBuffer(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        history._count += 1
        history._bytes_downloaded += 18
        index = _get_buffer_index(data)
        history.append(index, data)
        if history._count % 64 == 0:
            print(f'. ({history._count}, {history._bytes_downloaded}/{history._length})')
        else:
            print('.', end='')
    
class DoNothing(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        pass
    
class StoreHistoryFile(StateTransitionHandler):
    def __init__(self, path):
        self._path = path
        
    def do_transition(self, state_machine, device, history, data=None):
        if history._count % 64 != 0:
            print(f' ({history._count}, {history._bytes_downloaded}/{history._length})')
        #print('--')
        #print(f"File Length: {history._length}")
        #print(f"Device Time: {history._device_time}")
        #print(f"Session ID: {history._session_id}")
        #print(f"Measurement Period: {history._measurement_period}")
        #print(f"Session Start Index: {history._session_start_index}")
        #print(f"Last Entry Index: {history._last_entry_index}")
        #print(f"Number of Buffers: {history._count}")
        #print(f"Number of Entries: {history._number_entries}")
        history.store(self._path)
        print(f"Data saved in {self._path}")
        
    
class DoQuit(StateTransitionHandler):
    def do_transition(self, state_machine, device, history, data=None):
        device.stop()
        
#########################################################################

class StateTransition():
    def __init__(self, state_machine, from_state, event, to_state, handler):
        self.state_machine = state_machine
        self.from_state = from_state
        self.event = event
        self.to_state = to_state
        self.handler = handler
        
    def do_transition(self, device, history, data=None):
        self.handler.do_transition(self.state_machine, device, history, data)

        
class DownloadStateMachine():
    
    STATE_STANDBY = "standby"
    STATE_INITIALIZING_TIME = "initializing-time"
    STATE_INITIALIZING_SESSION_ID = "initializing-session-id"
    STATE_INITIALIZING_MEASUREMENT_PERIOD = "initializing-measurement-period"
    STATE_INITIALIZING_SESSION_START_INDEX = "initializing-session-start-index"
    STATE_INITIALIZING_LAST_ENTRY_INDEX = "initializing-last-entry-index"
    STATE_INITIALIZING_NUMBER_OF_ENTRIES = "initializing-number-entries"
    STATE_INITIALIZING_TX_BUFFER = "initializing-tx-buffer"
    STATE_INITIALIZING_TX_STATUS = "initializing-tx-status"
    STATE_INITIALIZING_TRANSFER_INDEX = "initializing-transfer-index"
    STATE_SETTING_RX_STATUS_TO_RECEIVING = "setting-rx-status-to-receiving"
    STATE_SETTING_RX_STATUS_TO_ACK = "setting-rx-status-to-ack"
    STATE_RECEIVING_FIRST_BUFFER = "expecting-first-buffer"
    STATE_RECEIVING_BUFFERS = "receiving-buffers"
    STATE_READING_TX_STATUS = "reading-tx-status"
    STATE_CHECKING_TX_STATUS_DURING_INIT = "checking-tx-status-during-init"
    STATE_CANCELLING_TRANSFER = "cancelling-transfer"
    STATE_CHECKING_TX_STATUS_DURING_TRANSFER = "checking-tx-status-during-transfer"
    STATE_WAITING_LED_ON = "waiting-led-on"
    STATE_WAITING_LED_OFF = "waiting-led-off"

    STATE_HELP = "help"
    
    EVENT_START = "start"
    EVENT_TIME = "received-time"
    EVENT_SESSION_ID = "received-session-id"
    EVENT_MEASUREMENT_PERIOD = "received-measurement-period"
    EVENT_SESSION_START_INDEX = "received-session-start-index"
    EVENT_LAST_ENTRY_INDEX = "received-last-entry-index"
    EVENT_NUMBER_OF_ENTRIES = "received-number-entries"
    EVENT_TX_BUFFER_NOTIFICATIONS_READY = "tx-buffer-notifications-ready"
    EVENT_TX_STATUS_NOTIFICATIONS_READY = "tx-status-notifications-ready"
    EVENT_TRANSFER_START_INDEX_READY = "transfer-start-index-ready"
    EVENT_RX_STATUS_READY = "rx-status-ready"
    EVENT_TX_BUFFER_DATA = "tx-buffer-data"
    EVENT_TX_STATUS = "received-tx-status"
    EVENT_TX_STATUS_IDLE = "received-tx-status-idle"
    EVENT_TX_STATUS_NOT_IDLE = "received-tx-status-not-idle"
    EVENT_TX_STATUS_WAITING_ACK = "event-tx-status-waiting-ack"
    EVENT_TX_STATUS_TRANSFERRING = "event-tx-status-transferring"
    EVENT_TX_STATUS_IDLE = "event-tx-status-idle"
    EVENT_LED_OK = "led-written-ok"
    
    def __init__(self, path):
        self._path = path
        self._device = None
        self._history = HistoryFile()
        self._state = self.STATE_STANDBY
        self._count = 0

        self._state_transitions = []
        
        self._add(self.STATE_STANDBY,
                  self.EVENT_START,
                  self.STATE_WAITING_LED_ON,
                  TurnLedOn())
        
        self._add(self.STATE_WAITING_LED_ON,
                  self.EVENT_LED_OK,
                  self.STATE_READING_TX_STATUS,
                  RequestTxStatus())
        
        self._add(self.STATE_READING_TX_STATUS,
                  self.EVENT_TX_STATUS,
                  self.STATE_CHECKING_TX_STATUS_DURING_INIT,
                  CheckTxStatusDuringInit())
        
        self._add(self.STATE_CHECKING_TX_STATUS_DURING_INIT,
                  self.EVENT_TX_STATUS_NOT_IDLE,
                  self.STATE_CANCELLING_TRANSFER,
                  CancelTransfer())
        
        self._add(self.STATE_CANCELLING_TRANSFER,
                  self.EVENT_RX_STATUS_READY,
                  self.STATE_INITIALIZING_TIME,
                  RequestTime())
        
        self._add(self.STATE_CHECKING_TX_STATUS_DURING_INIT,
                  self.EVENT_TX_STATUS_IDLE,
                  self.STATE_INITIALIZING_TIME,
                  RequestTime())
        
        self._add(self.STATE_INITIALIZING_TIME,
                  self.EVENT_TIME,
                  self.STATE_INITIALIZING_SESSION_ID,
                  DoBoth(InitializeTime(),
                         RequestSessionID()))
        
        self._add(self.STATE_INITIALIZING_SESSION_ID,
                  self.EVENT_SESSION_ID,
                  self.STATE_INITIALIZING_MEASUREMENT_PERIOD,
                  DoBoth(InitializeSessionID(),
                         RequestMeasurementPeriod()))
        
        self._add(self.STATE_INITIALIZING_MEASUREMENT_PERIOD,
                  self.EVENT_MEASUREMENT_PERIOD,
                  self.STATE_INITIALIZING_SESSION_START_INDEX,
                  DoBoth(InitializeMeasurementPeriod(),
                         RequestSessionStartIndex()))
        
        self._add(self.STATE_INITIALIZING_SESSION_START_INDEX,
                  self.EVENT_SESSION_START_INDEX,
                  self.STATE_INITIALIZING_LAST_ENTRY_INDEX,
                  DoBoth(InitializeSessionStartIndex(),
                         RequestLastEntryIndex()))
        
        self._add(self.STATE_INITIALIZING_LAST_ENTRY_INDEX,
                  self.EVENT_LAST_ENTRY_INDEX,
                  self.STATE_INITIALIZING_NUMBER_OF_ENTRIES,
                  DoBoth(InitializeLastEntryIndex(),
                         RequestNumberOfEntries()))
        
        self._add(self.STATE_INITIALIZING_NUMBER_OF_ENTRIES,
                  self.EVENT_NUMBER_OF_ENTRIES,
                  self.STATE_INITIALIZING_TX_BUFFER,
                  DoBoth(InitializeNumberOfEntries(),
                         RegisterForTxBufferNotifications()))
        
        self._add(self.STATE_INITIALIZING_TX_BUFFER,
                  self.EVENT_TX_BUFFER_NOTIFICATIONS_READY,
                  self.STATE_INITIALIZING_TX_STATUS,
                  RegisterForTxStatusNotifications())
        
        self._add(self.STATE_INITIALIZING_TX_STATUS,
                  self.EVENT_TX_STATUS_NOTIFICATIONS_READY,
                  self.STATE_INITIALIZING_TRANSFER_INDEX,
                  WriteTransferStartIndex())
        
        self._add(self.STATE_INITIALIZING_TRANSFER_INDEX,
                  self.EVENT_TRANSFER_START_INDEX_READY,
                  self.STATE_SETTING_RX_STATUS_TO_RECEIVING,
                  StartReceiving())
        
        self._add(self.STATE_SETTING_RX_STATUS_TO_RECEIVING,
                  self.EVENT_RX_STATUS_READY,
                  self.STATE_RECEIVING_FIRST_BUFFER,
                  PrepareForFirstBuffer())
        
        self._add(self.STATE_RECEIVING_FIRST_BUFFER,
                  self.EVENT_TX_STATUS,
                  self.STATE_RECEIVING_FIRST_BUFFER,
                  DoNothing())
        
        self._add(self.STATE_RECEIVING_FIRST_BUFFER,
                  self.EVENT_TX_BUFFER_DATA,
                  self.STATE_RECEIVING_BUFFERS,
                  HandleFirstBuffer())
        
        self._add(self.STATE_RECEIVING_BUFFERS,
                  self.EVENT_TX_BUFFER_DATA,
                  self.STATE_RECEIVING_BUFFERS,
                  HandleBuffer())
        
        self._add(self.STATE_RECEIVING_BUFFERS,
                  self.EVENT_TX_STATUS,
                  self.STATE_CHECKING_TX_STATUS_DURING_TRANSFER,
                  CheckTxStatusDuringTransfer())
        
        self._add(self.STATE_CHECKING_TX_STATUS_DURING_TRANSFER,
                  self.EVENT_TX_STATUS_WAITING_ACK,
                  self.STATE_SETTING_RX_STATUS_TO_ACK,
                  SendTxStatusAck())
        
        self._add(self.STATE_CHECKING_TX_STATUS_DURING_TRANSFER,
                  self.EVENT_TX_STATUS_TRANSFERRING,
                  self.STATE_RECEIVING_BUFFERS,
                  DoNothing())
        
        self._add(self.STATE_CHECKING_TX_STATUS_DURING_TRANSFER,
                  self.EVENT_TX_STATUS_IDLE,
                  self.STATE_WAITING_LED_OFF,
                  DoBoth(StoreHistoryFile(self._path),
                         TurnLedOff()))

        self._add(self.STATE_WAITING_LED_OFF,
                  self.EVENT_LED_OK,
                  self.STATE_STANDBY,
                  DoQuit())
        
        self._add(self.STATE_SETTING_RX_STATUS_TO_ACK,
                  self.EVENT_RX_STATUS_READY,
                  self.STATE_RECEIVING_BUFFERS,
                  DoNothing())
        
    def set_device(self, device):
        self._device = device
        
    def _add(self, from_, event, to, handler):
        self._state_transitions.append(StateTransition(self, from_, event, to, handler))
        
    def _get_transition(self, event):
        result = None
        for transition in self._state_transitions:
            if transition.from_state == self._state and transition.event == event:
                result = transition
                break
        return result
            
    def handle_event(self, event, data=None):
        transition = self._get_transition(event)
        if transition == None:
            raise ValueError(f"Failed to find transition for "
                             + f"state={self._state}, event={event}")
        self._state = transition.to_state
        transition.do_transition(self._device, self._history, data)
        #print(f"({transition.from_state}, {event}) -> {transition.to_state}")
                
    def handle_notifications_succeeded(self, characteristic):
        if characteristic == self._device.tx_buffer:
            self.handle_event(self.EVENT_TX_BUFFER_NOTIFICATIONS_READY)
        elif characteristic == self._device.tx_status:
            self.handle_event(self.EVENT_TX_STATUS_NOTIFICATIONS_READY)

    def handle_write_succeeded(self, characteristic):
        if characteristic == self._device.rx_status:
            self.handle_event(self.EVENT_RX_STATUS_READY)
        elif characteristic == self._device.transfer_start_index:
            self.handle_event(self.EVENT_TRANSFER_START_INDEX_READY)
        elif characteristic == self._device.led:
            self.handle_event(self.EVENT_LED_OK)

    def handle_value_updated(self, characteristic, data):
        if characteristic == self._device.tx_status:
            self.handle_event(self.EVENT_TX_STATUS, data)
            
        elif characteristic == self._device.tx_buffer:
            self.handle_event(self.EVENT_TX_BUFFER_DATA, data)
            
        elif characteristic == self._device.clock:
            self.handle_event(self.EVENT_TIME, data)
            
        elif characteristic == self._device.session_id:
            self.handle_event(self.EVENT_SESSION_ID, data)
            
        elif characteristic == self._device.measurement_period:
            self.handle_event(self.EVENT_MEASUREMENT_PERIOD, data)
            
        elif characteristic == self._device.session_start_index:
            self.handle_event(self.EVENT_SESSION_START_INDEX, data)

        elif characteristic == self._device.last_entry_index:
            self.handle_event(self.EVENT_LAST_ENTRY_INDEX, data)

        elif characteristic == self._device.number_entries:
            self.handle_event(self.EVENT_NUMBER_OF_ENTRIES, data)
        
class FlowerPower(gatt.Device):

    LIVE_SERVICE = "39e1fa00-84a8-11e2-afba-0002a5d5c51b"
    LIVE_SERVICE_LED = "39e1fa07-84a8-11e2-afba-0002a5d5c51b"

    CLOCK_SERVICE = '39e1fd00-84a8-11e2-afba-0002a5d5c51b'
    CLOCK_SERVICE_TIME = '39e1fd01-84a8-11e2-afba-0002a5d5c51b'

    HISTORY_SERVICE = "39e1fc00-84a8-11e2-afba-0002a5d5c51b"
    HISTORY_SERVICE_ENTRIES_NUMBER = "39e1fc01-84a8-11e2-afba-0002a5d5c51b";
    HISTORY_SERVICE_LAST_ENTRY_INDEX = "39e1fc02-84a8-11e2-afba-0002a5d5c51b"
    HISTORY_SERVICE_TRANSFER_START_INDEX = "39e1fc03-84a8-11e2-afba-0002a5d5c51b"
    HISTORY_SERVICE_SESSION_ID = "39e1fc04-84a8-11e2-afba-0002a5d5c51b"
    HISTORY_SERVICE_SESSION_START_INDEX = "39e1fc05-84a8-11e2-afba-0002a5d5c51b"
    HISTORY_SERVICE_SESSION_PERIOD = "39e1fc06-84a8-11e2-afba-0002a5d5c51b"

    UPLOAD_SERVICE = "39e1fb00-84a8-11e2-afba-0002a5d5c51b"
    UPLOAD_SERVICE_TX_BUFFER = "39e1fb01-84a8-11e2-afba-0002a5d5c51b"
    UPLOAD_SERVICE_TX_STATUS = "39e1fb02-84a8-11e2-afba-0002a5d5c51b"
    UPLOAD_SERVICE_RX_STATUS = "39e1fb03-84a8-11e2-afba-0002a5d5c51b"
    
    TX_IDLE = 0
    TX_TRANSFERRING = 1
    TX_AWAITING_ACK = 2
    
    RX_STANDBY = 0
    RX_RECEIVING = 1
    RX_ACK = 2
    RX_NACK = 3
    RX_CANCEL = 4
    RX_ERROR = 5
    
    
    def __init__(self, state_machine, *args, **kwargs):
        super(FlowerPower, self).__init__(*args, **kwargs)
        self._state_machine = state_machine
        self._led = None
        self._clock = None
        self._session_id = None
        self._measurement_period = None
        self._session_start_index = None
        self._last_entry_index = None
        self._number_entries = None
        self._tx_start_index = None
        self._tx_buffer = None
        self._tx_status = None
        self._rx_status = None
        self._state_machine.set_device(self)
        
    def log(self, message) -> None:
        print(f"FlowerPower[{self.mac_address}]: {message}")

    def stop(self) -> None:
        self.manager.stop()

    def connect_succeeded(self):
        super().connect_succeeded()
        self.log("Connected")

    def connect_failed(self, error):
        super().connect_failed(error)
        self.log(f"Connection failed: {str(error)}")
        self.stop()

    def disconnect_succeeded(self):
        super().disconnect_succeeded()
        self.log("Disconnected")
        self.stop()

    def services_resolved(self):
        super().services_resolved()
        self.run_state_machine()
        
    def register_notifications(self, characteristic):
        characteristic.enable_notifications()
        
    def write_byte(self, characteristic, value):
        characteristic.write_value(bytearray([value]))
        
    def write_u32(self, characteristic, value):
        characteristic.write_value(bytearray(value.to_bytes(4, 'little')))
        
    def read(self, characteristic):
        characteristic.read_value()
        
    def run_state_machine(self):
        self._state_machine.handle_event(DownloadStateMachine.EVENT_START)

    @property
    def clock(self):
        if self._clock == None:
            self._clock = self._get(self.CLOCK_SERVICE, self.CLOCK_SERVICE_TIME)
        return self._clock

    @property
    def session_id(self):
        if self._session_id == None:
            self._session_id = self._get(self.HISTORY_SERVICE,
                                         self.HISTORY_SERVICE_SESSION_ID)
        return self._session_id

    @property
    def measurement_period(self):
        if self._measurement_period == None:
            self._measurement_period = self._get(self.HISTORY_SERVICE,
                                                 self.HISTORY_SERVICE_SESSION_PERIOD)
        return self._measurement_period
    
    @property
    def session_start_index(self):
        if self._session_start_index == None:
            self._session_start_index = self._get(self.HISTORY_SERVICE,
                                                  self.HISTORY_SERVICE_SESSION_START_INDEX)
        return self._session_start_index
    
    @property
    def last_entry_index(self):
        if self._last_entry_index == None:
            self._last_entry_index = self._get(self.HISTORY_SERVICE,
                                               self.HISTORY_SERVICE_LAST_ENTRY_INDEX)
        return self._last_entry_index
    
    @property
    def number_entries(self):
        if self._number_entries == None:
            self._number_entries = self._get(self.HISTORY_SERVICE,
                                               self.HISTORY_SERVICE_ENTRIES_NUMBER)
        return self._number_entries
    
    @property
    def transfer_start_index(self):
        if self._tx_start_index == None:
            self._tx_start_index = self._get(self.HISTORY_SERVICE,
                                             self.HISTORY_SERVICE_TRANSFER_START_INDEX)
        return self._tx_start_index
    
    @property
    def led(self):
        if self._led == None:
            self._led = self._get(self.LIVE_SERVICE, self.LIVE_SERVICE_LED)
        return self._led
    
    @property
    def tx_buffer(self):
        if self._tx_buffer == None:
            self._tx_buffer = self._get(self.UPLOAD_SERVICE, self.UPLOAD_SERVICE_TX_BUFFER)
        return self._tx_buffer
    
    @property
    def tx_status(self):
        if self._tx_status == None:
            self._tx_status = self._get(self.UPLOAD_SERVICE, self.UPLOAD_SERVICE_TX_STATUS)
        return self._tx_status
    
    @property
    def rx_status(self):
        if self._rx_status == None:
            self._rx_status = self._get(self.UPLOAD_SERVICE, self.UPLOAD_SERVICE_RX_STATUS)
        return self._rx_status
        
    def _get(self, service_uuid, characteristic_uuid):
        service = next(
            s for s in self.services
            if s.uuid == service_uuid)
        if not service:
            raise ValueError(f"Can't find service {service_uuid}")
        characteristic = next(
            c for c in service.characteristics
            if c.uuid == characteristic_uuid)
        if not characteristic:
            raise ValueError(f"Can't find characteristic {characteristic_uuid}")
        return characteristic
        
    def characteristic_enable_notifications_succeeded(self, characteristic):
        self._state_machine.handle_notifications_succeeded(characteristic)
        
    def characteristic_enable_notifications_failed(self, characteristic):
        self.log("characteristic_enable_notification_failed")
        self.stop()

    def characteristic_value_updated(self, characteristic, value):
        #print("characteristic_value_updated " + characteristic.uuid + ": " + str(value))
        self._state_machine.handle_value_updated(characteristic, value)

    def characteristic_write_value_succeeded(self, characteristic):
        self._state_machine.handle_write_succeeded(characteristic)

    def characteristic_write_value_failed(self, characteristic, error):
        self.log("Write failed: " + characteristic.uuid + " " + str(error))
        self.stop()



class FlowerPowerManager(gatt.DeviceManager):
    def __init__(self, macaddress, state_machine, *args, **kwargs):
        super(FlowerPowerManager, self).__init__(*args, **kwargs)
        self._start_time = time.time()
        self._macaddress = macaddress
        self._state_machine = state_machine
        self._flower_power = None
        
    def device_discovered(self, device):
        if self._this_is_the_one(device):
            self.stop_discovery()
            self._connect_to_flower_power(device)
        elif self._timed_out(): 
            self.stop()

    def _this_is_the_one(self, device):
        return (device.mac_address == self._macaddress
                and self._flower_power == None)
            
    def _timed_out(self):
        return (self._flower_power == None
                and time.time() - self._start_time > 30)
        
    def _connect_to_flower_power(self, device):
        print("Connecting")
        self._flower_power = FlowerPower(self._state_machine, manager=self,
                                         mac_address=self._macaddress) 
        self._flower_power.connect()

        
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("address")
    parser.add_argument("file")
    args = parser.parse_args()
    
    macaddress = args.address
    path = args.file

    state_machine = DownloadStateMachine(path)
    manager = FlowerPowerManager(macaddress, state_machine, adapter_name='hci0')
    manager.start_discovery()
    manager.run()
