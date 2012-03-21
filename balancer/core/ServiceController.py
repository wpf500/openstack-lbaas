# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import logging
import uuid

from balancer.common.utils import Singleton
from openstack.common import exception

logger = logger = logging.getLogger(__name__)


class ServiceTask():
        def __init__(self,  worker):
            self._name = None
            #TODO make autogenerated id
            self._id = uuid.uuidl().hex
            self._params = None
            self._status = "PENDING"
            self._type = worker.type
            self._worker = worker
            self.lock = threading.Lock()
        
        @property
        def type(self):
            return self._type
            
        @property
        def id(self):
            return self._id
        
        @id.setter
        def id(self,  value):
            self._id = value
        
        @property
        def parameters(self):
            return self._params
        
        @parameters.setter
        def parameters(self,  value):
            self._params = value
        
        def addParameter(self,  name,  value):
            self._params[name] = value
        
        @property
        def status(self):
            self.lock.acquire()
            status = self._status
            self.lock.release()
            return status
        
        @status.setter
        def status(self,  value):
            self.lock.acquire()
            self._status = value
            self.lock.release()
        

@Singleton
class ServiceController():
          
        
    def __init__(self):
        logger.debug("Service controller instance created.")
        self._tasks = {}
        self.lock = threading.Lock()
    
    def getTaskStatus(self,  id):
        #TODO thread safe ?
        self.lock.acquire()
        try:
            task = self._tasks.get(id,  None)
        
            if task == None:
                raise exception.NotFound()
        finally: 
           self.lock.release()           
        return task.status()
        
    def addTask(self,  task):
        self.lock.acquire()
        try:
            self._tasks[task.id] = task
        finally: 
           self.lock.release()           
    
    def execute(self,  action,  params):
        #TODO add logic here
        pass
        