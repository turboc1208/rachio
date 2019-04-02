import appdaemon.plugins.hass.hassapi as hass
import datetime
import time
import requests
from requests.auth import HTTPDigestAuth

from rachiopy import Rachio
from rachiopy import Notification
from rachiopy import Device

class rachio(hass.Hass):

  def initialize(self):
    # self.LOGLEVEL="DEBUG"
    self.log("rachio App")
    ADUtils=self.get_app("ADutils")
    self.zones={}
    self.webhooks={}

    # get configuration from apps.yaml
    if "url" in self.args:
      self.response_url=self.args['url']
      #self.response_url='https://hass2.hass.dnsalias.com/api/appdaemon/rachio'
    else:
      self.log("url must be specified in apps.yaml")

    if "apikey" in self.args:
      apikey=self.args['apikey']
    else:
      self.log("apikey must be specified in apps.yaml")

    if 'devices' in self.args:
      self.devices=self.args['devices']
      #self.prettyPrint(self.devices,'',0)
    else:
      self.log("Devices must be setup in apps.yaml")

    self.webhook_name="ZONE_STATUS_EVENT"

    # register endpoing for webhooks to come in on 
    self.register_endpoint(self.handle_webhooks,"rachio")

    # setup rachiopy objects
    self.r = Rachio(apikey)
    self.n = Notification(self.r)
    self.d = Device(self.r)

    # build a dictionary of available webhook event types (not really sure if I need to do this but its here if we need it)
    h,res=self.n.getWebhookEventType()

    for h in range(len(res)):
      self.webhooks[res[h]['name']]={'webhookid':res[h]['id']}

    # get person information
    h,id=self.r.person.getInfo()
    h,info2=self.r.person.get(id["id"])

    # with Rachio, a person has one or more device.  The device is your controller.  Each device/controller has one or more zones.
    # loop through devices ( d )
    for d in range(len(info2["devices"])):
      zonecount=0
      # cleanup old webhooks before registering new ones
      self.cleanup_webhooks(info2["devices"][d]['id'])
      # you only need one webhook per device so we will register it here
      #self.log("Registering for {}-{} webhook on device {} at url {}".format(self.webhooks[self.webhook_name]['webhookid'],self.webhook_name,info2["devices"][d]['id'],self.response_url))
      res=self.n.postWebhook(info2['devices'][d]['id'],"rachio_zones",self.response_url,[{'id':self.webhooks[self.webhook_name]['webhookid']}])

      # loop through zones
      for z in range(len(info2["devices"][d]["zones"])):
        tempZone=info2["devices"][d]["zones"][z]
        if tempZone["enabled"]==True:
          zoneName=tempZone["name"]
          zonecount=zonecount+1

          # register state callback on each of the input_number components so we can handle it if its turned on or off
          self.log("registering callback for -{}-".format(self.devices[zoneName]['switch']))
          h=self.listen_state(self.switch_cb,self.devices[zoneName]['switch'])

          # build a zone dictionary to reference the zones later on.
          self.zones[zoneName]={"enabled":tempZone["enabled"],"zoneid":tempZone["id"],"image":tempZone["imageUrl"],
                                "deviceid":info2["devices"][d]['id'],"switch_name":self.devices[zoneName]['switch'],
                                "sensor_name":self.devices[zoneName]['sensor'],"listener_handle":h}

      #self.prettyPrint(self.zones,"",0)       

      #debugging messages to verify if webhooks got registered
      #h,res=self.n.getDeviceWebhook(info2["devices"][d]['id'])
      #self.log("what webhooks are registered - {}".format(res))


  ######################
  #
  # find_zone - based on a HA switch_name (input_number's in our case)
  #
  ######################
  def find_zone(self,entity):
    # loop through zones dictionary looking for a zone that has the passed in entity as the switch_name
    for d in self.zones:
      if self.zones[d]['switch_name']==entity:
        return d
    return none


  #####################
  #
  #  switch_cb  - callback to handle when the input_number slider moves to a new value
  #
  #####################
  def switch_cb(self,entity,state,old,new,kwargs):
    self.log("entity - {} changed from {} to {}".format(entity,old, new))
    # if the value changed, we stop watering.
    h,res=self.d.getCurrentSchedule(self.zones[self.find_zone(entity)]['deviceid'])
    if res!={}:
      # We have a schedule running
      #self.log("we have a schedule running {}".format(res))
      if res['zoneId']!=self.zones[self.find_zone(entity)]['zoneid']:
        # the current schedule is not for the zone we are changing so stop the water.
        self.log("changing from {} to {} zones so turn water off".format(res['zoneId'],self.zones[self.find_zone(entity)]['zoneid']))
        self.d.stopWater(self.zones[self.find_zone(entity)]['deviceid'])
        self.log("Preparing to start {}".format(self.zones[self.find_zone(entity)]["zoneid"]))

        # input_numbers are in minutes, zone.start wants duration in seconds, so remember to multiply by 60
        h,res=self.r.zone.start(self.zones[self.find_zone(entity)]["zoneid"],int(float(new))*60)
        #self.log("h={}, res={}".format(h,res))
      else:
        if float(new)>0:
          # if the new value is greater than 0, then we still want the water on.  We have already turned it off, so turn it back on.
          #self.log("Preparing to start {}".format(self.zones[self.find_zone(entity)]["zoneid"]))

          # input_numbers are in minutes, zone.start wants duration in seconds, so remember to multiply by 60
          #h,res=self.r.zone.start(self.zones[self.find_zone(entity)]["zoneid"],int(float(new))*60)
          #self.log("h={}, res={}".format(h,res))
          pass
        else:
          self.log("changing duration to 0 so turn it off")
          self.d.stopWater(self.zones[self.find_zone(entity)]['deviceid'])
    else:
      if float(new)>0:
        self.log("Preparing to start {}".format(self.zones[self.find_zone(entity)]["zoneid"]))

        # input_numbers are in minutes, zone.start wants duration in seconds, so remember to multiply by 60
        h,res=self.r.zone.start(self.zones[self.find_zone(entity)]["zoneid"],int(float(new))*60)
        #self.log("h={}, res={}".format(h,res))
      else:
        self.log("not sure how I got here, supposedly there isn't any schedule running but we got a command to turn the zone off")
        self.d.stopWater(self.zones[self.find_zone(entity)]['Deviceid'])

  #################
  #
  #  cleanup_webhooks - webhooks are registered on the rachio server, so if our app doesn't clean up behind itself,
  #                     make sure we remove all old webhooks so we can go forward cleanly
  #
  #################
  def cleanup_webhooks(self,device_id):
    self.log("cleaning up webhooks")
    # get a list of webhooks
    h,res=self.n.getDeviceWebhook(device_id)

    # loop through webhooks, we will use our url as the key to use when cleaning up.
    for wh in range(len(res)):
      if res[wh]['url'].find(self.response_url)>=0:
        h,res2=self.n.deleteWebhook(res[wh]['id'])

  ################
  #
  # handle_webhooks - this is the meat of the app, we handle rachio telling us what's going on.
  #
  ################
  def handle_webhooks(self,data):
    #self.log("webhook data = {}".format(data))

    if data['type']=="ZONE_STATUS":
      self.log("data[type]={}, data[zoneid]={}, data[zoneName]={}, data[zoneRunState]={}".format(data['type'],data['zoneId'],data['zoneName'],data['zoneRunState']))
      if data['zoneRunState']=="STARTED":

        # set sensor values accordingly.  This updates statuses of the sensor and input number if the zone was turned on some other way
        self.set_state(self.zones[data['zoneName']]['sensor_name'],state='On')
        h,res = self.d.getCurrentSchedule(data['deviceId'])
        #self.log("res={}".format(res))
        if res=={}:
          zoneduration=0
        else:
          zoneduration=float(res['zoneDuration'])/60
        self.log("schedule zoneduration={}".format(zoneduration))
        if not int(zoneduration)==int(float(self.get_state(self.zones[data['zoneName']]['switch_name']))):
          self.log("updating {} from {} to current rachio duration {}".format(self.zones[data['zoneName']]['switch_name'],self.get_state(self.zones[data['zoneName']]['switch_name']),zoneduration))
          self.set_state(self.zones[data['zoneName']]['switch_name'],state=zoneduration,internal=True)
      # handle STOPPED and COMPLETED both turn off the sensor and set the input_number back to 0
      elif data['zoneRunState']=="STOPPED":  # - manually stopped
        self.set_state(self.zones[data['zoneName']]['sensor_name'],state='Off')
        self.set_state(self.zones[data['zoneName']]['switch_name'],state=0)
      elif data['zoneRunState']=="COMPLETED":  # - scheduled event ended
        self.set_state(self.zones[data['zoneName']]['sensor_name'],state='Off')
        self.set_state(self.zones[data['zoneName']]['switch_name'],state=0)
      else:
        self.log("unknown runstate - {}".format(data['zoneRunState']))
    # always return 200 from a webhook handler unless there is an error
    return "", 200

  #############
  #
  # prettyPrint - walk a directory or list tree printing out value in a somewhat organized method.
  #
  #############
  def prettyPrint(self,ob,parent,indent):
    if type(ob) is list or type(ob) is dict:
      if type(ob) is dict:
        self.log("{} {}".format(" " * indent,parent))
        for o in ob:
          self.prettyPrint(ob[o],o,indent+1)
      else:
        self.log("{} {}".format(" " * indent,parent))
        for i in range(len(ob)):
          self.prettyPrint(ob[i],parent,indent+1)
    else:
      self.log("{} {}-{}".format(" " * indent,parent,ob))

  def terminate(self):
    self.log("terminating app")
    for z in self.zones:
      self.log("removing listener for {}".format(self.zones[z]['switch_name']))
      self.cancel_listen_state(self.zones[z]['listener_handle'])
    self.cleanup_webhooks(self.zones[list(self.zones.keys())[0]]['deviceid'])

