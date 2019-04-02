#rachio

This is an appdaemon version of the rachio component.  It uses webhooks to keep from having to poll.

Requirements : rachiopy  https://github.com/rfverbruggen/rachiopy/tree/master/rachiopy
               setup the api_port in the hass configuration in the appdaemon config file.
Other links : Rachio's API documentation   https://rachio.readme.io/docs/getting-started

Things that are helpful to understand.
1. Rachio thinks of things in a hierarchey.
    1. Person
        1. Device
            1. Zone
            1. Schedule
            1. Notifications
1. A person can have one or more devices.
1. Devices are the controllers that all your sprinkler zones are wired into.
1. Devices have Zones, Schedules and Notifications
    1. Zones are the lowest level rachio knows about.  Zones have physical sprinkler heads attached to them, but rachio doesn't know about those.
    1. Schedules are setup in the rachio app and tell rachio when to run each zone, how long it's supposed to run.  Schedules also track realtime
          progress when something is running.  Even a manual "quick run" creates a schedule and tracks it's progress using a schedule.  If you 
          want to find out the current status of a zone, check the currently running schedule.
    1. Notifications are webhooks that send your app a message when something happens.  You will need some type of async loop that waits for
          messages without blocking the rest of your app to manage these.  Appdaemon provides the rest api or the api I get confused which
          is for which to accomplish this for you.

Installation:
* put this in a subdirectory of your appdaemon code directory.
* install rachiopy in a directory where it can be found by the python package search.
* create input_number entries for each of your zones in your HomeAssistant (HA) configuration.yaml file.
```
    input_number:
      back_away_switch:
        initial: 0
        min: 0
        max: 60
        step: 1
      front_boundary_switch:
        initial: 0
        min: 0
        max: 60
        step: 1
```
In your apps.yaml file add the following section with the appropriate substitutions.

    rachio:
      class: rachio
      module: rachio
      apikey: bunch of letters and numbers you can get from the rachio app
      url: https://my.external.domain.com/api/appdaemon/rachio
      devices:
        'Back Away': 
          switch: input_number.back_away_switch 
          sensor: binary_sensor.back_away_sensor
        'Back Left New': 
          switch: input_number.back_left_new_switch
          sensor: binary_sensor.back_left_new_sensor

* the url is the address that rachio's cloud servers will send any notifications to.
* the url has to end with /api/appdaemon/rachio.
* Whether it's https or http and your domain name are specific to your configuration
* The devices section starts with the name of your rachio zone (this is case sensitive).  
indented under that are the HA switch names and HA sensor names you setup in your configuration.yaml file earlier.  
Switches should be input_numbers and sensors should be binary_sensors.
