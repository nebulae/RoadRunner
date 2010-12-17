#!/usr/bin/env python
import datetime
import logging
import os
import random
import re
import gdata
import gdata.docs
import gdata.docs.service
import gdata.docs.client
import string

from django.utils import simplejson
from google.appengine.api import channel
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
from StringIO import StringIO
from string import join

class Connection(db.Model):
    person = db.UserProperty()
    channelKey = db.StringProperty() 
    latitude = db.FloatProperty()
    longitude = db.FloatProperty()
    
class UserAndLocation():
    person = None
    latitude = None
    longitude = None
    def toJson(self):
        return { 'person' : self.person.nickname(), 'latitude': self.latitude, 'longitude' : self.longitude}
    
    
class UsersResponse():
    action = "display_users";
    users = None;
    
    def get_users(self):
        return self.users
    
    def get_users_json(self):
        strings = [];
        for user in self.users:
            strings.append(user.toJson())
        return strings
    
    def dispatch(self):
        people_query = Connection.all();          
        self.users = [];
        for connection in people_query:
            ul = UserAndLocation();
            ul.person = connection.person
            ul.latitude = connection.latitude
            ul.longitude = connection.longitude
            self.users.append(ul);

        people_query = Connection.all();
        response = {
                    'action': self.action, 
                    'users' : self.get_users_json()
        }; 
        
        for connection in people_query:
            logging.log(logging.INFO, "to " + connection.channelKey + ": " + simplejson.dumps(response))
            channel.send_message(connection.channelKey, simplejson.dumps(response));
    
class ConnectionClosed(webapp.RequestHandler):
    def post(self):
        key = self.request.get('g');
        connectionToClose = Connection.gql("where channelKey='" + key + "'");
        
        for connection in connectionToClose:
            connection.delete();
        
        ur = UsersResponse();
        ur.dispatch();
    
class Handshake(webapp.RequestHandler):
    def post(self):
#        get the key from the request
        key = self.request.get('g');
        lat = self.request.get('latitude');
        lng = self.request.get('longitude');
        c = Connection.gql("where channelKey='" + key + "'");
        for connection in c:
            connection.latitude = float(lat)
            connection.longitude = float(lng)
            db.put(connection)
        
        ur = UsersResponse();
        ur.dispatch();
      
class GetConnectedUsers:
    def get(self):
        people_query = Connection.all();       
        respo = [];
        for connection in people_query:
            respo.append(connection.person.nickname());
        
        self.response.out.write(respo);
        
class Dispatcher(webapp.RequestHandler):
    def get(self):
        user = users.GetCurrentUser()
        if user:
            url = users.create_logout_url(self.request.uri)
            url_linktext = 'Logout'
            userkey = addConnection();
            token = channel.create_channel(userkey)
            template_values = {
                               'url': url,
                               'token' : token,
                               'key': userkey,
                               'url_linktext': url_linktext,
                               'initial_message': 'foo!',
                               'nickname' : user.nickname()
            }
            path = os.path.join(os.path.dirname(__file__), 'index.html')
            self.response.out.write(template.render(path, template_values))
        else : 
            url = users.create_login_url(self.request.uri)
            self.redirect(url)

             
    
              
class MainPage(webapp.RequestHandler):
    def get(self):
        
        user = users.get_current_user()
        client = gdata.docs.client.DocsClient(source='eveny-nebulae-v1')
        client.ClientLogin("trinity.testbot@gmail.com", "!@#$qwer", client.source)
        documents_feed = client.GetDocList(uri='/feeds/default/private/full/-/pending')
        if user:
            url = users.create_logout_url(self.request.uri)
            url_linktext = 'Logout'
            userkey = addConnection();
            token = channel.create_channel(userkey)
            template_values = {
                               'url': url,
                               'token' : token,
                               'documents' : documents_feed,
                               'key': userkey,
                               'url_linktext': url_linktext,
                               'initial_message': 'foo!',
                               'nickname' : user.nickname()
            }

            path = os.path.join(os.path.dirname(__file__), 'index.html')
            self.response.out.write(template.render(path, template_values))
        else:
            url = users.create_login_url(self.request.uri)
            self.redirect(url)
              
        
def addConnection():
    user = users.get_current_user()
    if user:
            userkey = user.user_id()
            connection = Connection(key_name = userkey);
            connection.person = user
            connection.channelKey = userkey;
            connection.put();
            return userkey;
          
              
application = webapp.WSGIApplication([('/', MainPage),
                                      ('/handshake', Handshake),
                                      ('/dispatchview', Dispatcher),
                                      ('/closed', ConnectionClosed),
                                      ('/users', GetConnectedUsers)],debug=True)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()