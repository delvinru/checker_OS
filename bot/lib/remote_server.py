import json
from datetime import datetime

import dateutil.parser
import pytz
import requests
from loguru import logger

from lib.settings import (
    REMOTE_SERVER, 
    REMOTE_SERVER_LOGIN,
    REMOTE_SERVER_PASSWORD
)


class RemoteServer:
    def __init__(self):
        self.url = REMOTE_SERVER
        self.header = {
            "accept" : "application/json",
            "Content-Type": "application/json"
        }
        self.login = REMOTE_SERVER_LOGIN
        self.password = REMOTE_SERVER_PASSWORD
        self.session = requests.Session()
        self.session_url = self.url + "session"
        self.telegram_url = self.url + "telegram"
        self.init_session = False
    
    def __init_session(self):
        data = json.dumps({
            "login" : self.login,
            "password" : self.password
        })
        try:
            r = self.session.post(self.session_url, headers=self.header, data=data).json()
        except:
            logger.warning("Server error in __init_session")
            return None

        self.secure_token = r['secure_token']
        self.time_of_death = r['time_of_death']
        self.init_session = True
    
    def __extend_session(self):
        new_url = self.session_url + self.secure_token
        r = self.session.put(new_url, data={"accept":"application/json"}).json()
        self.secure_token = r['secure_token']
        self.time_of_death = r['time_of_death']

    def __check_session(self):
        """
        Check session for rest api user
        If session was not initialized or completed than extend session 
        """

        if not self.init_session:
            self.__init_session()

        server = dateutil.parser.isoparse(self.time_of_death)
        tz = pytz.timezone('Europe/Paris')
        now = datetime.now(tz).replace(tzinfo=None)
        offset = (now - server).seconds
        # Update token every 30 minute
        if offset > 1800:
            self.__extend_session()
        # If session die renew
        elif offset > 3500:
            self.__init_session()
    
    def init_user(self, telegram_id=None, id_card=None):
        """
        Init user on remote server
        """

        self.__check_session()

        data = json.dumps({
            "secure_token" : self.secure_token,
            "telegram_id" : telegram_id,
            "login" : id_card
        })

        r = self.session.post(self.telegram_url, headers=self.header, data=data).json()
        if r['result']:
            logger.info(f"User init on server: {telegram_id} {id_card}")
            return True
        else: 
            logger.warning(f"User not init on server: {r}")
            return False
        
    def mark_user(self, telegram_id=None):
        """
        Send data to remote server for mark user
        """

        self.__check_session()

        data = json.dumps({
            "secure_token" : self.secure_token,
            "telegram_id" : telegram_id,
            "simulate" : False
        })

        r = self.session.put(self.telegram_url, headers=self.header, data=data).json()

        if r['result']:
            logger.info(f"User marked in server: {telegram_id}")
            return True
        else: 
            logger.warning(f"User not marked in server. Error: {r}")
            return False
    
    def search_user(self, telegram_id=None):
        """
        Find user by telegram id on remote server
        """

        self.__check_session()

        data = json.dumps({
            "secure_token" : self.secure_token,
            "telegram_id" : telegram_id,
            "simulate" : True
        })

        r = self.session.put(self.telegram_url, headers=self.header, data=data).json()

        if r['result']:
            if not r.get('name'):
                return None

            logger.info(f"Find user on server: {r['name']}")
            return r['name']
        else:
            logger.info(f"User {telegram_id} not found on server")
            return None