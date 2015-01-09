#####################################################################
#                                                                   #
# /plugins/labwatch/__init__.py                                     #
#                                                                   #
# Copyright 2014, Monash University                                 #
#                                                                   #
# This file is part of the program BLACS, in the labscript suite    #
# (see http://labscriptsuite.org), and is licensed under the        #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################


import logging
import os
import subprocess
import sys
import threading

import zmq
import json

if 'PySide' in sys.modules.copy():
    from PySide.QtCore import *
    from PySide.QtGui import *
else:
    from PyQt4.QtCore import *
    from PyQt4.QtGui import *

from qtutils import *

FILEPATH_COLUMN = 0
name = "LabWatch"
module = "labwatch" # should be folder name
logger = logging.getLogger('BLACS.plugin.%s'%module)

class Plugin(object):
    def __init__(self,initial_settings):
        self.menu = None
        self.notifications = {}
        self.initial_settings = initial_settings
        
    def get_menu_class(self):
        return None
        
    def get_notification_classes(self):
        return [Notification]
    
    def get_setting_classes(self):
        return [Setting]
        
    def get_callbacks(self):
        return {'settings_changed':self.notifications[Notification].setup_labwatch}
        
    def set_menu_instance(self,menu):
        self.menu = menu
        
    def set_notification_instances(self,notifications):
        self.notifications = notifications
        
    def plugin_setup_complete(self):
        self.notifications[Notification].setup_labwatch()
        

    
    def get_save_data(self):
        return None
    
    def close(self):
        self.notifications[Notification].close()
        
        

class Notification(object):
    name = name
    def __init__(self, BLACS):
        # set up the lab watching
        self.BLACS = BLACS
        self.labwatch = None
        
        # Create the widget
        self._ui = UiLoader().load(os.path.join(os.path.dirname(os.path.realpath(__file__)),'notification.ui'))
        self.notification_label = self._ui.notification_label
        # self._ui.hide()
            
    def get_widget(self):
        return self._ui
        
    def get_properties(self):
        return {'can_hide':True, 'can_close':True, 'closed_callback':self.setup_labwatch}
        
    def set_functions(self,show_func,hide_func,close_func,get_state):
        self._show = show_func
        self._hide = hide_func
        self._close = close_func
        self._get_state = get_state
                
          
    def setup_labwatch(self):
        monitor_list = self.BLACS['settings'].get_value(Setting,'monitored_devices')
        zmq_server = self.BLACS['settings'].get_value(Setting,'host')
        zmq_port = self.BLACS['settings'].get_value(Setting,'port')
        
        
        if self.labwatch:
            self.labwatch.stop()
        
        #only start if we have a server to connect to!
        if zmq_server and zmq_port:
            logger.info("Launching LabWatch")
            self.labwatch = Labwatch(monitor_list,zmq_server,zmq_port,self.pause_queue,self._show,self.notification_label)
        
    def pause_queue(self):
        self.BLACS['experiment_queue'].manager_paused = True
    
    def close(self):
        self.labwatch.stop()
        
class Setting(object):
    name = name

    def __init__(self,data):
        # This is our data store!
        self.data = data
        
        
        if 'monitored_devices' not in self.data:
            self.data['monitored_devices'] = {}
            
        if 'host' not in self.data:
            self.data['host'] = ''
        
        if 'port' not in self.data:
            self.data['port'] = ''
            
        #set the default sort order if it wasn't previously saved
        if 'monitored_devices_sort_order' not in self.data:
            self.data['monitored_devices_sort_order'] = "ASC"
        
    # Create the page, return the page and an icon to use on the label (the class name attribute will be used for the label text)   
    def create_dialog(self,notebook):
        self.ui = UiLoader().load(os.path.join(os.path.dirname(os.path.realpath(__file__)),'labwatch.ui'))
        
        # Create the models, get the views, and link them!!
  
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(['',''])

        self.view = self.ui.monitor_treeview
        self.view.setModel(self.model)
        
        
        
        self.model.itemChanged.connect(self.on_item_changed)
        
        self.dummy_sensors = []
        self.dummy_id_keys = []
        self.checks_items = []
        
        
        ## Restore saved data
        #monitored_devices = {host:{sensor:{identifiers:{},checks:{key:'',state:'',min:'',max:''}}}}
        for host in self.data['monitored_devices'].keys():
            host_item = QStandardItem(host)
            host_item.setEditable(True)
            self.model.appendRow(host_item)
            
            for sensor in self.data['monitored_devices'][host].keys():
                sensor_item = QStandardItem(sensor)
                sensor_item.setEditable(True)
                host_item.appendRow([sensor_item])
                
                identifiers_item = self.create_identifiers_item(sensor_item)
                
                for id_key in self.data['monitored_devices'][host][sensor]['identifiers'].keys():
                    id_key_item = QStandardItem(id_key)
                    id_key_item.setEditable(True)
                    id_value_item = QStandardItem(self.data['monitored_devices'][host][sensor]['identifiers'][id_key])
                    id_value_item.setEditable(True)
                    identifiers_item.appendRow([id_key_item,id_value_item])
                self.create_dummy_identifier(identifiers_item)
                
                checks_item = self.create_checks_item(sensor_item,key=self.data['monitored_devices'][host][sensor]['checks']['key'],value=self.data['monitored_devices'][host][sensor]['checks']['state'],min=self.data['monitored_devices'][host][sensor]['checks']['min'],max=self.data['monitored_devices'][host][sensor]['checks']['max'])
                
                self.view.setExpanded(self.model.indexFromItem(host_item),True)
                self.view.setExpanded(self.model.indexFromItem(sensor_item),True)
                self.view.setExpanded(self.model.indexFromItem(identifiers_item),True)
                self.view.setExpanded(self.model.indexFromItem(checks_item),True)
             
        self.ui.hostname_text.setText(self.data['host'])
        self.ui.port_text.setText(self.data['port'])
        
        self.dummy_host = QStandardItem('<click to add host device>')
        self.dummy_host.setEditable(True)
        self.dummy_host.setToolTip('Add a new host device here')
        blank_item = QStandardItem("")
        blank_item.setEditable(False)
        self.model.appendRow([self.dummy_host,blank_item])
        self.view.resizeColumnToContents(0)
        self.view.resizeColumnToContents(1)
        return self.ui,None
    
    
    def on_item_changed(self,item):
        if item is self.dummy_host:
            if item.text()=="<click to add host device>":
                return
            if len(self.model.findItems(item.text())) > 1:
                self.dummy_host.setText("<click to add host device>")
                messagebox = QMessageBox()
                messagebox.setText("This host name is already being monitored")
                messagebox.setWindowTitle("Warning")
                messagebox.setIcon(QMessageBox.Warning)
                messagebox.exec_()
                return
            
            
            #give the new host a dummy child
            self.create_dummy_sensor(item)
            
            
            self.view.setExpanded(self.model.indexFromItem(item),True)
            
            # Make a new dummy item to replace the one we used
            items = []
            self.dummy_host = QStandardItem('<click to add host device>')
            self.dummy_host.setEditable(True)
            self.dummy_host.setToolTip('Add a new host device here')
            items.append(self.dummy_host)
            self.model.appendRow(items)
            item.setToolTip(None)
        if self.item_in_list(item,self.dummy_sensors):
            if item.text()=="<click to add sensor>":
                return
                
            host_item = item.parent()
            identical_items = -1
            for child_index in range(host_item.rowCount()):
                if host_item.child(child_index).text() == item.text():
                    identical_items += 1
            if identical_items:
                item.setText("<click to add sensor>")
                messagebox = QMessageBox()
                messagebox.setText("This sensor is already being monitored")
                messagebox.setWindowTitle("Warning")
                messagebox.setIcon(QMessageBox.Warning)
                messagebox.exec_()
                return
            
            #remove the old dummy sensor from the list and make a new one
            
            self.remove_item_from_list(item,self.dummy_sensors)
            self.create_dummy_sensor(host_item)
            
            #create the items for the new sensor's settings
            identifiers_item = self.create_identifiers_item(item)
            
            
            self.create_dummy_identifier(identifiers_item)
            
            
            checks_item = self.create_checks_item(item)
            
            
            
            
            self.view.setExpanded(self.model.indexFromItem(item),True)
            self.view.setExpanded(self.model.indexFromItem(identifiers_item),True)
            self.view.setExpanded(self.model.indexFromItem(checks_item),True)
            
        
        if self.item_in_list(item,self.dummy_id_keys):
            if item.text()=="<key>":
                return
                
            host_item = item.parent()
            identical_items = -1
            for child_index in range(host_item.rowCount()):
                if host_item.child(child_index).text() == item.text():
                    identical_items += 1
            if identical_items:
                item.setText("<key>")
                messagebox = QMessageBox()
                messagebox.setText("This key is already being monitored. You can type in multiple values (with spaces inbetween) if you want to look for more than one value on this key")
                messagebox.setWindowTitle("Warning")
                messagebox.setIcon(QMessageBox.Warning)
                messagebox.exec_()
                return
            #remove the old dummy key from the list and make a new one
            
            self.remove_item_from_list(item,self.dummy_id_keys)
            self.create_dummy_identifier(host_item)
        
        if self.item_in_list(item.parent(),self.checks_items):
            # Row 1 is the allowed state/values box. If this has something in it then we should make the min/max non editable.
            if item.index().row() == 1 and item.index().column()==1:
                if item.text() == "":
                    item.parent().child(2,1).setEditable(True)
                    item.parent().child(3,1).setEditable(True)
                    item.parent().child(2,0).setEnabled(True)
                    item.parent().child(3,0).setEnabled(True)
                else:
                    item.parent().child(2,1).setEditable(False)
                    item.parent().child(3,1).setEditable(False)
                    item.parent().child(2,0).setEnabled(False)
                    item.parent().child(3,0).setEnabled(False)
            # row 2 is min, row 3 is max
            if (item.index().row() == 2 or item.index().row() == 3)  and item.index().column()==1:
                if item.text() != "":
                    # check that the user has put in a number!
                    try:
                        f = float(item.text())
                    except:
                        item.setText("")
                        messagebox = QMessageBox()
                        messagebox.setText("Min/max values should be numbers.")
                        messagebox.setWindowTitle("Warning")
                        messagebox.setIcon(QMessageBox.Warning)
                        messagebox.exec_()
                        return
                    #if setting the min value, make sure it's less than max:
                    if item.index().row() ==2 and item.parent().child(3,1).text() != "" and float(item.text()) > float(item.parent().child(3,1).text()):
                        item.setText("")
                        messagebox = QMessageBox()
                        messagebox.setText("Min should be less than max!")
                        messagebox.setWindowTitle("Warning")
                        messagebox.setIcon(QMessageBox.Warning)
                        messagebox.exec_()
                        return
                    #if setting the max value, make sure it's more than min:
                    if item.index().row() ==3 and item.parent().child(2,1).text() != "" and float(item.text()) < float(item.parent().child(2,1).text()):
                        item.setText("")
                        messagebox = QMessageBox()
                        messagebox.setText("Max should be less than max!")
                        messagebox.setWindowTitle("Warning")
                        messagebox.setIcon(QMessageBox.Warning)
                        messagebox.exec_()
                        return
                if item.parent().child(2,1).text() == '' and item.parent().child(3,1).text() =='':
                    item.parent().child(1,1).setEditable(True)
                    item.parent().child(1,0).setEnabled(True)
                else:
                    item.parent().child(1,1).setEditable(False)
                    item.parent().child(1,0).setEnabled(False)
                    
        self.view.resizeColumnToContents(0)
        self.view.resizeColumnToContents(1)
    
    def remove_item_from_list(self,item,list):
        to_delete = None
        for i, list_item in enumerate(list):
            if item is list_item:
                to_delete = i
                break
    
        if to_delete is not None:
            del list[to_delete]
            return True
            
        return False
        
                
    def item_in_list(self,item,list):
        for i in list:
            if i is item:
                return True
        return False
        
    def create_dummy_sensor(self, parent):
        dummy_sensor = QStandardItem('<click to add sensor>')
        dummy_sensor.setEditable(True)
        dummy_sensor.setToolTip('Add a new host device here')
        self.dummy_sensors.append(dummy_sensor)
        parent.appendRow([dummy_sensor])
    
    def create_dummy_identifier(self,parent):
        dummy_id_key = QStandardItem('<key>')
        dummy_id_key.setEditable(True)
        dummy_id_key.setToolTip('Add a new key to look for')
        self.dummy_id_keys.append(dummy_id_key)
        dummy_id_value = QStandardItem('<value>')
        dummy_id_value.setEditable(True)
        dummy_id_value.setToolTip('Specify the value required')
        
        
        parent.appendRow([dummy_id_key,dummy_id_value])
        
    def create_identifiers_item(self,parent):
        identifiers_item = QStandardItem('Identifiers:')
        identifiers_item.setEditable(False)
        identifiers_item.setToolTip('Optional key value pairs to look for in the syslog message to identify this sensor.')
        blank_item = QStandardItem("")
        blank_item.setEditable(False)
        parent.appendRow([identifiers_item,blank_item])
        
        return identifiers_item
    
    def create_checks_item(self,parent,key='',value='',min='',max=''):
        checks_item = QStandardItem('Checks:')
        checks_item.setEditable(False)
        checks_item.setToolTip('Specify the value/condition associated with this sensor that you want to check.')
        parent.appendRow([checks_item])
        self.checks_items.append(checks_item)
        
        check_key_label_item = QStandardItem('Key:')
        check_key_label_item.setEditable(False)
        check_key_label_item.setToolTip('Specify the key associated with the measurement value/condition that you want to check.')
        check_key_item = QStandardItem(key)
        check_key_item.setEditable(True)
        check_key_item.setToolTip('Specify the key associated with the measurement value/condition that you want to check.')
        checks_item.appendRow([check_key_label_item,check_key_item])
        
        check_value_label_item = QStandardItem('Allowed state/value(s):')
        check_value_label_item.setEditable(False)
        check_value_label_item.setToolTip('Specify the allowed value/condition(s) that you want to check. If you use this option you cannot use min/max.')
        check_value_item = QStandardItem(value)
        check_value_item.setToolTip('Specify the allowed value/condition(s) that you want to check. If you use this option you cannot use min/max.')
        if min or max:
            check_value_label_item.setEnabled(False)
            check_value_item.setEditable(False)
        else:
            check_value_item.setEditable(True)
        
        checks_item.appendRow([check_value_label_item,check_value_item])
        
        check_min_label_item = QStandardItem('Minimum:')
        check_min_label_item.setEditable(False)
        check_min_label_item.setToolTip('Specify the minimum allowable value for the measurement you\'re checking. If you use this option you cannot set allowed state/value(s).')
        check_min_item = QStandardItem(min)
        check_min_item.setToolTip('Specify the minimum allowable value for the measurement you\'re checking. If you use this option you cannot set allowed state/value(s).')
        if value:
            check_min_label_item.setEnabled(False)
            check_min_item.setEditable(False)
        else:
            check_min_item.setEditable(True)
        checks_item.appendRow([check_min_label_item,check_min_item])
        
        
        check_max_label_item = QStandardItem('Maximum:')
        check_max_label_item.setEditable(False)
        check_max_label_item.setToolTip('Specify the maximum allowable value for the measurement you\'re checking. If you use this option you cannot set allowed state/value(s).')
        check_max_item = QStandardItem(max)
        
        check_max_item.setToolTip('Specify the maximum allowable value for the measurement you\'re checking. If you use this option you cannot set allowed state/value(s).')
        if value:
            check_max_label_item.setEnabled(False)
            check_max_item.setEditable(False)
        else:
            check_max_item.setEditable(True)
        checks_item.appendRow([check_max_label_item,check_max_item])
        
        return checks_item
    
    def get_value(self,name):
        if name in self.data:
            return self.data[name]
        
        return None
    
    def save(self):
        # transfer the contents of the treeview into the data store, and then return the data store
        
        #monitored_devices = {host:{sensor:{identifiers:{},checks:{key:'',state:'',min:'',max:''}}}}
        self.data['monitored_devices']={}
        for host_index in range(self.model.rowCount()):
            host_item =  self.model.item(host_index,0)
            hostname = str(host_item.text())
            if hostname == "<click to add host device>":
                continue
            self.data['monitored_devices'][hostname]={}
            for sensor_index in range(host_item.rowCount()):
                sensor_item = host_item.child(sensor_index,0)
                sensorname = str(sensor_item.text())
                if sensorname == "<click to add sensor>":
                    continue
                self.data['monitored_devices'][hostname][sensorname]={"identifiers":{},"checks":{}}
                identifiers_item = sensor_item.child(0,0)
                for id_index in range(identifiers_item.rowCount()):
                    key = str(identifiers_item.child(id_index,0).text())
                    if key == "<key>":
                        continue
                    value = str(identifiers_item.child(id_index,1).text())
                    
                    self.data['monitored_devices'][hostname][sensorname]["identifiers"][key]=value
                    
                checks_item = sensor_item.child(1,0)
                for check_index in range(checks_item.rowCount()):
                    key = checks_item.child(check_index,0).text()
                    if key == 'Key:':
                        key = 'key'
                        value = str(checks_item.child(check_index,1).text())
                    elif key == "Allowed state/value(s):":
                        key = 'state'
                        value = str(checks_item.child(check_index,1).text())
                        
                    elif key == "Minimum:":
                        key = "min"
                        value = str(checks_item.child(check_index,1).text())
                    elif key == "Maximum:":
                        key = "max"
                        value = str(checks_item.child(check_index,1).text())
                    
                    self.data['monitored_devices'][hostname][sensorname]["checks"][key]=value
                    
        # we also want to save the host name and port
        self.data['host'] = str(self.ui.hostname_text.text())
        self.data['port'] = str(self.ui.port_text.text())
        return self.data
        
    def close(self):
        pass
        
        
class Labwatch(object):

    def __init__(self,monitor_list,zmq_server,zmq_port,pause_queue,show_notification,notification_text_widget):
        self.monitor_list = monitor_list
        
        # functions and widgets for pausing queue, showing notification and changing what is says:
        self.pause_queue = pause_queue
        self.show_notification = lambda: inmain(show_notification)
        self.notification_text_widget = notification_text_widget
        
        self.running = True
        # #set up a dictionary to store the latest alert level and value of each sensor we want to monitor:
        # self.latest_values = {host:{sensor:{'AlertLevel':7,'value':None} for sensor in self.monitor_list[host].keys()} for host in self.monitor_list.keys()}
        
        # insert keys into the monitor list where we can save the current status of each device being monitored, in the form "status":{"level:AlertLevel, "value":(value of key being monitored)}
        for host in self.monitor_list.values():
            for sensor in host.values():
                sensor['status'] = {'level':7, 'value': None}
        
        # a reference for converting between numerical error levels and human readable messages. Note that we are introducing an extra level at -1 called "Out of bounds" for when values are ouside of the acceptable range set in the BLACS preferences.
        self.errorlevels = {-1:"Out of bounds",0:"Emergency",1:"Alert",2:"Critical",3:"Error",4:"Warning",5:"Notice",6:"Info",7:"Debug"}
        
        ctx = zmq.Context()
        self.sub = ctx.socket(zmq.SUB)
        
        for name in monitor_list.keys():
            self.sub.setsockopt(zmq.SUBSCRIBE,name)
        logger.info('connecting to zmq server')
        self.sub.connect('tcp://%s:%s'%(zmq_server,zmq_port))
        
        logger.info('Launching zmq reading thread')
        self.sub_thread = threading.Thread(target=self.parse_syslog)
        self.sub_thread.daemon = True
        self.sub_thread.start()
        
        self.error_state = False
    
    def parse_syslog(self):
        while self.running:
            [name,severity,timestamp,status]=self.sub.recv_multipart()
            status_dict = json.loads(status)
            severity = int(severity)
            # Check to see if we care about the device who sent the latest message:
            if self.monitor_list.has_key(name):
                # now check to see if any of the identifying keys for sensors on this host have come up in the message
                
                for sensor in self.monitor_list[name].values():
                    for identifier in sensor['identifiers'].keys():
                        if status_dict.has_key(identifier):
                            if status_dict[identifier] in sensor['identifiers'][identifier]:
                                # This message relates to our sensor, so now check what the alert level of the sensor is, and if the  value we care about is included then log it too
                                # We only want to update the alert level if it is worse than the previously recorded one, this way if the problem goes away the message in BLACS will still say what went wrong, so the user knows why the queue was paused.
                                self.update_value_from_syslog(sensor,status_dict,severity)
                         
                    # if there are no identifiers for this host then I suppose we should treat all messages from the host as being related to the sensor                
                    if len(sensor['identifiers']) == 0:
                        self.update_value_from_syslog(sensor,status_dict,severity)
            if self.error_state:
                # One or more sensor is bad! The queue should have been paused already, but we need to update the text on the notification panel and display it.\
                notification_message = ""
                for host in self.monitor_list.values():
                    for sensor_name,sensor_data in host.iteritems():
                        if sensor_data['status']['level'] < 4:
                            notification_message += "%s is (or was) in %s state. Latest value is %s.\n" %(sensor_name,self.errorlevels[sensor_data['status']['level']], sensor_data['status']['value'])
                inmain(self.notification_text_widget.setText,notification_message)
                self.show_notification()
            
    def update_value_from_syslog(self,sensor,status_dict,severity):
        if severity < sensor['status']['level']:
            sensor['status']['level'] = severity
            if severity < 4:
                self.pause_queue()
        if status_dict.has_key(sensor['checks']['key']):
            sensor['status']['value'] = status_dict[sensor['checks']['key']]
            # now check to see if this is an allowed value. If not, give it a severity of -1 to say that it's out of BLACS's bounds
            if sensor['checks']['state']:
                if sensor['checks']['state'][0] == "[":
                    state = eval(sensor['checks']['state'],{})
                    if sensor['status']['value'] not in state:
                        sensor['status']['level'] = -1
                        self.pause_queue()
                elif sensor['status']['value'] != ensor['checks']['state']:
                    sensor['status']['level'] = -1
                    self.pause_queue()
            if sensor['checks']['min']:
                if float(sensor['status']['value']) < float(sensor['checks']['min']):
                    sensor['status']['level'] = -1
                    self.pause_queue()
            if sensor['checks']['max']:
                if float(sensor['status']['value']) > float(sensor['checks']['max']):
                    sensor['status']['level'] = -1
                    self.pause_queue()
        if sensor['status']['level'] < 4:
            # We've got a problem!
            self.error_state = True
    def stop(self):
        self.running = False
    
if __name__ == "__main__":
    app = QApplication([])
    s = Setting({})
    ui,_ = s.create_dialog(None)
    ui.show()
    
    app.exec_()
    
