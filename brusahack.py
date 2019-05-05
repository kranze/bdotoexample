#!/usr/bin/python

import paho.mqtt.client as mqtt
import time, threading
import logging, sys

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

TOPIC_PP_STATE = "port0/pp/state"
TOPIC_CP_DUTY_CYCLE = "port0/cp/duty_cycle"

class ChargeControl(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)

        #logging stuff
        logger.setLevel(logging.DEBUG)        
        logger.info("logger init complete")

        self.client=mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message 
        self.client.connect("localhost", 1883, 60)
        self.client.publish("port0/cp/duty_cycle", 0, retain=True)

        self.clientex=mqtt.Client()
        self.clientex.on_connect = self.on_connectex
        self.clientex.on_message = self.on_messageex
        self.clientex.connect("solarbuntumiv", 1883, 60) #IP address EVAcharge
        self.clientex.loop_start()
        
        self.alive=True
        
        self.cpstate=''
        self.cpdebounce=0
        self.diode_present=False
        
        self.cable_pp=0
        self.evse_duty_cycle=0
        self.max_cable_current=0
        self.evse_pwm_current=0
        self.pwm=0
        
    def on_connect(self, client, userdata, flags, rc):

        if (rc == 0):
            logger.info("Connected with result code "+str(rc))
        else:
            logger.error("Connected with result code "+str(rc))
            
        client.subscribe("port0/#")
#        client.subscribe("watchdog/ping")
    
    def on_message(self, client, userdata, msg):

        logger.info( "on_message: " + msg.topic+" "+str(msg.payload) )
        
        if (msg.topic == "watchdog/ping"):
             self.client.publish("watchdog/pong", "iec61851d %s"%msg.payload, retain=False)

        elif (msg.topic == "port0/cp/state"):
             if (msg.payload in ['A','B','C','D','E','F']):
                self.cpstate=msg.payload
             else:
                self.cpstate='E'
             logger.info("CP State: " + msg.payload)
 
        elif(msg.topic == "port0/diode_present"):
            self.diode_present=(msg.payload=="1")
            logger.debug("Diode present: "+ self.diode_present)

    
    def on_connectex(self, client, userdata, flags, rc):

        if (rc == 0):
            logger.info("ConnectedEx with result code "+str(rc))
        else:
            logger.error("ConnectedEx with result code "+str(rc))

        client.subscribe("port0/#")

    def on_messageex(self, client, userdata, msg):
        
        logger.debug( "on_message: " + msg.topic+" "+str(msg.payload) )
        
        if (msg.topic == TOPIC_PP_STATE):
            try:
                self.cable_pp = int(msg.payload)
            except:
                self.cable_pp = 0
            self.max_cable_current = self.map_pp(self.cable_pp)
        
        elif (msg.topic == TOPIC_CP_DUTY_CYCLE):
            try:
                self.evse_duty_cyle = int(msg.payload)
            except:
                self.evse_duty_cyle = -1
            self.evse_pwm_current = self.calc_pwm_current( self.evse_duty_cyle )
            
                
    def map_pp(self, value):
    
        if ( value == 1 ):
            return(13)
        elif(value == 2):
            return(20)
        elif(value == 3):
            return(32)
        elif(value == 4):
            return(63)
        else:
            return(0)
    
    def calc_pwm_current(self, value):

        if ( value >= 8 and value < 10 ):
            return( 6 )
        elif ( value >= 10 and value < 85 ):
            return( int( value * 0.6 ) )
        elif ( value >= 86 and value < 96 ):
            return( int( ( value - 64 ) * 2.5 ) )
        elif ( value == 97 ):
            return( 80 )
        else:
            return ( 0 )
    
    def calc_current_pwm(self, value):

        if ( value >= 6 and value < 52 ):
            return( int( value / 0.6 )  )
        elif ( value >= 52 and value < 80 ):
            return( int( value / 2.5 ) + 64 )
        elif ( value >= 80 ):
            return( 97 )
        else:
            return ( 0 )
                      
    def die(self):
        
        self.alive=False
        time.sleep(0.2)
        self.client.publish("port0/cp/duty_cycle", 0, retain=True)
        self.client.publish("port0/contactor/state/target", 0, retain=True)
        self.clientex.publish("port0/cp/state", 'B', retain=True)
        self.clientex.loop_stop()
    
    def pp_for_brusa(self, value):
        
        self.client.publish("port0/contactor/state/target", value, retain=True)

        
    def run(self):

        cpstate_old=''
        max_cable_current_old=0
        pwm=0

        while self.alive:
            time.sleep(0.1)
            if( max_cable_current_old != self.max_cable_current ):
                if ( self.max_cable_current > 0 ):
                    self.pp_for_brusa( 1 )
                else:
                    self.pp_for_brusa( 0 )
                max_cable_current_old = self.max_cable_current
                
            if ( self.evse_pwm_current > 0 ):
                self.max_current_for_brusa = min( self.max_cable_current, self.evse_pwm_current )
                pwm = ( self.calc_current_pwm( self.max_current_for_brusa ) )
            else:
                pwm = 0

            if (True or cpstate_old != self.cpstate):        
                if (self.cpstate == 'C' and self.diode_present):
                    self.clientex.publish("port0/cp/state", 'C', retain=False)
                else:
                    self.clientex.publish("port0/cp/state", 'B', retain=False)
                cpstate_old = self.cpstate

            if ( self.pwm != pwm ):
                self.client.publish("port0/cp/duty_cycle", pwm, retain=False)
                self.pwm=pwm
            
        

if (__name__ == "__main__"):
    CCo = ChargeControl()
    CCo.start()

    try:
        CCo.client.loop_forever()
    except:
        raise
    finally:
        CCo.die()
