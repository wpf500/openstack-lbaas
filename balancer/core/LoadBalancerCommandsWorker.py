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
import sys
import threading

from balancer.core.Worker import *

class LBGetIndexWorker(SyncronousWorker):
    def __init__(self,  task):
         super(LBGetIndexWorker, self).__init__(task)
    
    def execute(self):
        pass


class CreateLBWorker(ASyncronousWorker):
        def __init__(self,  task):
            super(CreateLBWorker, self).__init__(task)
        
        def run(self):
            self._task.status = STATUS_PROGRESS
            try:
                params = self._task.parameters
                
                driver = params['driver']
                
                nodes = params['nodes']
                
                sf = params['serverfarm']
                
                createSF(sf)
                
                for node in nodes:
                    createRServer(sf, node)
                
                probes = params['probes']
                
                for probe in probes:
                    createProbe(probe)
                    attachProbeToSF(sf,  probe)
                
                vserver = params['vserver']
                
                createVServer(vserver,  sf)
            except exception:
                self._task.status = STATUS_ERROR
                #TODO Do rollback. We need command pattern here
            
            self._task.status = STATUS_DONE
            
            
            
              