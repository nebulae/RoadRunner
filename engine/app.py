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

from django.utils import simplejson
from google.appengine.api import channel
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

class Connection(db.Model):
    person = db.UserProperty()
    channelKey = db.StringProperty() 
    
class UsersResponse():
    action = "display_users";
    users = None;
    
    def get_users(self):
        return self.users
    
    def dispatch(self):
        people_query = Connection.all();          
        self.users = [];
        for connection in people_query:
            self.users.append(connection.person.nickname());
        people_query = Connection.all();
        response = "{action: '"+self.action+"', users : "+simplejson.dumps(self.users)+"}"; 
        for connection in people_query:
            channel.send_message(connection.channelKey, response);
    
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
        user = users.get_current_user();
#        send the welcome to the user
        channel.send_message(key, "{ message : 'welcome " + user.nickname() + "' }");
#        send the notification to everyone else
        ur = UsersResponse();
        ur.dispatch();
      
class GetConnectedUsers:
    def get(self):
        people_query = Connection.all();       
        respo = [];
        for connection in people_query:
            respo.append(connection.person.nickname());
        
        self.response.out.write(simplejson.dumps(respo));
        
              
class MainPage(webapp.RequestHandler):
    def get(self):
        
        user = users.get_current_user()
        client = gdata.docs.client.DocsClient(source='eveny-nebulae-v1')
        client.ClientLogin("trinity.testbot@gmail.com", "!@#$qwer", client.source)
        documents_feed = client.GetDocList(uri='/feeds/default/private/full/-/pending')
        if user:
            url = users.create_logout_url(self.request.uri)
            url_linktext = 'Logout'
            userkey = user.user_id()
#create the new connection to store 
            connection = Connection(key_name = userkey);
            connection.person = user
            connection.channelKey = userkey;
            connection.put();
            token = channel.create_channel(user.user_id())
            template_values = {
                               'url': url,
                               'token' : token,
                               'documents' : documents_feed,
                               'key': user.user_id(),
                               'url_linktext': url_linktext,
                               'initial_message': 'foo!',
                               'nickname' : user.nickname()
            }

            path = os.path.join(os.path.dirname(__file__), 'index.html')
            self.response.out.write(template.render(path, template_values))
        else:
            url = users.create_login_url(self.request.uri)
            self.redirect(url)
              
              
              
application = webapp.WSGIApplication([('/', MainPage),
                                      ('/handshake', Handshake),
                                      ('/closed', ConnectionClosed),
                                      ('/users', GetConnectedUsers)],debug=True)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()