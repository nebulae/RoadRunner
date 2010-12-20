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
import urllib

from django.utils import simplejson
from google.appengine.api import channel
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
from StringIO import StringIO
from string import join
from uuid import uuid1
from google.appengine.api import urlfetch


#this is the pub / club / bar etc... 
class Location(db.Model):
    name = db.StringProperty()
    address = db.PostalAddressProperty()
    latitude = db.FloatProperty()
    longitude = db.FloatProperty()
    person = db.UserProperty()
    placekey = db.StringProperty()
    
class Customer(db.Model):
    name = db.StringProperty()
    autoOrder = db.StringProperty()
    notes = db.StringListProperty()
    currentLocations = db.ReferenceProperty()
    person = db.UserProperty()

class Connection(db.Model):
    person = db.UserProperty()
    channelKey = db.StringProperty() 
    latitude = db.FloatProperty()
    longitude = db.FloatProperty()
    
class LocationsUpdate():
    action = "display_locations";
    def dispatch(self, placekey = None):
        locations = [];
        if(placekey != None):
            location_query = Location.gql("where placekey='" + placekey + "'");
        else:
            location_query = Location.all();
        
        for location in location_query:
            locations.append({
                              'name': location.name, 
                              'address' : location.address, 
                              'latitude' : location.latitude,
                              'longitude' : location.longitude,
                              'placekey' : location.placekey 
                              }
            );
        people_query = Connection.all();
        response = { 'action': self.action, 'locations' : locations }
        for connection in people_query:
            logging.log(logging.INFO, "to " + connection.channelKey + ": " + simplejson.dumps(response))
            channel.send_message(connection.channelKey, simplejson.dumps(response));
        
                        
          
class UserAndLocation():
    person = None
    latitude = None
    longitude = None
    def toJson(self):
        return { 
                'person' : self.person.nickname(), 
                'latitude': self.latitude, 
                'longitude' : self.longitude
        }
        
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
            if(len(str(lat))>0): 
                connection.latitude = float(lat)
            if(len(str(lng))>0): 
                connection.longitude = float(lng)
            db.put(connection)
        
        ur = UsersResponse();
        ur.dispatch();
#        lr = LocationsUpdate();
#        lr.dispatch();
        
class AddAddress(webapp.RequestHandler):
    def post(self):
        address = self.request.get('address');
        name = self.request.get('name');
        key = self.request.get('g');
        querystring = { 'address' : address, 'sensor' : 'false' }
        url = "http://maps.googleapis.com/maps/api/geocode/json?" + urllib.urlencode(querystring)
        
        result = urlfetch.fetch(url)
        res = simplejson.loads(result.content)
        if(res['results'][0] != None):
            lat = res['results'][0]['geometry']['location']['lat']
            lon = res['results'][0]['geometry']['location']['lng']
            address_formatted = res['results'][0]['formatted_address']
            logging.log(logging.INFO, name)
            placekey = addLocation(name, address_formatted, lat, lon)
            response = { 
                    'action': "display_address_lookup", 
                    'results' : "congrats!  you have successfully added your location.",
                    'placekey' : placekey
                    }
            channel.send_message(key, simplejson.dumps(response))
            update = LocationsUpdate()
            update.dispatch(placekey)
        else: 
            response = { 
                    'action': "display_address_lookup", 
                    'results' : "The address could not be found.  please check the address and try again." 
                    }
            channel.send_message(key, simplejson.dumps(response))
          
class AddLocation(webapp.RequestHandler):
    def post(self):
        key = self.request.get('g');
        name = self.request.get('name');
        address = self.request.get('address');
        placekey = addLocation(name, address)
        update = LocationsUpdate()
        update.dispatch(placekey)
        
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

class Join(webapp.RequestHandler):
    def get(self):
        user = users.GetCurrentUser()
        if user:
            url = users.create_logout_url(self.request.uri)
            url_linktext = 'Logout'
            userkey = user.user_id();
            token = channel.create_channel(userkey)
            template_values = {
                               'url': url,
                               'url_linktext': url_linktext,
                               'token' : token,
                               'key': userkey,
                               'templateType' : "join",
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
        locations = Location.all()
        if user:
            url = users.create_logout_url(self.request.uri)
            url_linktext = 'Logout'
            userkey = addConnection();
            token = channel.create_channel(userkey)
            template_values = {
                               'url': url,
                               'token' : token,
                               'documents' : documents_feed,
                               'locations' : locations,
                               'key': userkey,
                               'url_linktext': url_linktext,
                               'initial_message': 'foo!',
                               'templateType' : "index",
                               'nickname' : user.nickname()
            }

            path = os.path.join(os.path.dirname(__file__), 'index.html')
            self.response.out.write(template.render(path, template_values))
        else:
            url = users.create_login_url(self.request.uri)
            self.redirect(url)
                  
def addLocation(name, address, lat, lon):
    user = users.get_current_user()
    if(user):
        placekey = str(uuid1())
        location = Location(key_name = placekey)
        location.person = user
        location.name = name
        location.placekey = placekey
        location.address = address
        location.latitude = lat
        location.longitude = lon
        location.put()
        return placekey    
    
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
                                      ('/lookupaddress', AddAddress),
                                      ('/addme', AddLocation),
                                      ('/join', Join),
                                      ('/dispatchview', Dispatcher),
                                      ('/closed', ConnectionClosed),
                                      ('/users', GetConnectedUsers)],debug=True)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()