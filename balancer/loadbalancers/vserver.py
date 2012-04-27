# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack LLC.
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

import balancer.common.utils
import logging
import openstack.common.exception
#from balancer.loadbalancers.command import BaseCommand
import balancer.storage.storage

import loadbalancer
import predictor
import probe
import realserver
import serverfarm
import vlan
import virtualserver
import sticky

logger = logging.getLogger(__name__)


class Balancer():
    def __init__(self):

        """ This member contains LoadBalancer object """
        self.lb = None
        self.sf = None
        self.rs = []
        self.probes = []
        self.vips = []
        self.store = balancer.storage.storage.Storage()

    def parseParams(self, params):

        #if (params.has_key('lb')):
        if 'lb' in params.keys():
            lb = params['lb']
        else:
            lb = loadbalancer.LoadBalancer()
        lb.loadFromDict(params)
        self.lb = lb
        self.lb.status = loadbalancer.LB_BUILD_STATUS
        nodes = params.get('nodes',  None)
        sf = serverfarm.ServerFarm()
        sf.lb_id = lb.id
        sf._predictor = createPredictor(lb.algorithm)
        
        sf._predictor.sf_id = sf.id
        
        sf.name = sf.id
        self.sf = sf
        device_id = params.get('device_id',  None)
        logger.debug("Device ID = %s" % device_id)
        if device_id != None:
            self.lb.device_id = device_id

        """ Parse RServer nodes and attach them to SF """
        if nodes != None:
            for node in nodes:
                rs = realserver.RealServer()
                rs.loadFromDict(node)
                # We need to check if there is already real server  with the same IP deployed
                rd = self.store.getReader()
                try:
                    parent_rs = rd.getRServerByIP(rs.address)
                except openstack.common.exception.NotFound:
                    parent_rs=None
                    pass
                if balancer.common.utils.checkNone(parent_rs):
                    if parent_rs.address != "":
                       rs.parent_id = parent_rs.id
                
                rs.sf_id = sf.id
                rs.name = rs.id
                self.rs.append(rs)
                self.sf._rservers.append(rs)

        probes = params.get("healthMonitor",  None)
        if probes != None:
            for pr in probes:
                prb = createProbe(pr['type'])
                prb.loadFromDict(pr)
                prb.sf_id = sf.id
                prb.name = prb.id
                self.probes.append(prb)
                self.sf._probes.append(prb)

        vips = params.get('virtualIps',  None)

        if vips != None:
            for vip in vips:
                vs = virtualserver.VirtualServer()
                vs.loadFromDict(vip)
                vs.proto = lb.transport
                vs.appProto = lb.protocol
                vs.sf_id = sf.id
                vs.lb_id = lb.id
                vs.name = vs.id
                self.vips.append(vs)

        stic = params.get("sessionPersistence",  None)
        
        if stic != None:
            for st in stic:
                st = createSticky(stic['type'])
                st.loadFromDict(stic)
                st.sf_id = sf.id
                st.name = st.id
                self.sf._sticky.append(st)

    def update(self):
        store = balancer.storage.storage.Storage()
        wr = store.getWriter()
        wr.updateObjectInTable(self.lb)
        
        for st in self.sf._sticky:
            wr.updateObjectInTable(st)
        for rs in self.rs:
            wr.updateObjectInTable(rs)

        for pr in self.probes:
            wr.updateObjectInTable(pr)

        for vip in self.vips:
            wr.updateObjectInTable(vip)

    def getLB(self):
        return self.lb

    def savetoDB(self):
        store = balancer.storage.storage.Storage()
        wr = store.getWriter()

        wr.writeLoadBalancer(self.lb)
        wr.writeServerFarm(self.sf)
        wr.writePredictor(self.sf._predictor)

        for rs in self.rs:
            wr.writeRServer(rs)

        for pr in self.probes:
            wr.writeProbe(pr)

        for vip in self.vips:
            wr.writeVirtualServer(vip)

        for st in self.sf._sticky:
            wr.writeSticky(st)

    def loadFromDB(self, lb_id):
        store = balancer.storage.storage.Storage()
        rd = store.getReader()
        self.lb = rd.getLoadBalancerById(lb_id)
        self.sf = rd.getSFByLBid(lb_id)
        sf_id = self.sf.id
        predictor = rd.getPredictorBySFid(sf_id)
        self.sf._predictor = predictor
        self.rs = rd.getRServersBySFid(sf_id)
        sticks = rd.getStickiesBySFid(sf_id)

        for rs in self.rs:
            self.sf._rservers.append(rs)
        self.probes = rd.getProbesBySFid(sf_id)
        for prob in self.probes:
            self.sf._probes.append(prob)
        self.vips = rd.getVIPsBySFid(sf_id)
        for st in sticks:
            self.sf._sticky.append(st)

    def removeFromDB(self):
        store = balancer.storage.storage.Storage()
        dl = store.getDeleter()
        lb_id = self.lb.id
        sf_id = self.sf.id
        dl.deleteLBbyID(lb_id)
        dl.deleteSFbyLBid(lb_id)
        dl.deletePredictorBySFid(sf_id)

        dl.deleteRSsBySFid(sf_id)
        dl.deleteProbesBySFid(sf_id)
        dl.deleteVSsBySFid(sf_id)
        dl.deleteStickiesBySFid(sf_id)

#    def deploy(self,  driver,  context):
#        #Step 1. Deploy server farm
#        if  driver.createServerFarm(context,  self.sf) != "OK":
#            raise exception.OpenstackException
#
#        #Step 2. Create RServers and attach them to SF
#
#        for rs in self.rs:
#            driver.createRServer(context,  rs)
#            driver.addRServerToSF(context,  self.sf,  rs)
#
#        #Step 3. Create probes and attache them to SF
#        for pr in self.probes:
#            driver.createProbe(context,  pr)
#            driver.addProbeToSF(context,  self.sf,  pr)
#        #Step 4. Deploy vip
#        for vip in self.vips:
#            driver.createVIP(context,  vip,  self.sf)


def makeCreateLBCommandChain(bal,  driver,  context):
    list = []

    for pr in bal.probes:
        list.append(CreateProbeCommand(driver,  context,  pr))

    list.append(CreateServerFarmCommand(driver, context,  bal.sf))
    for rs in bal.rs:
        list.append(CreateRServerCommand(driver,  context, rs))
        list.append(AddRServerToSFCommand(driver, context, bal.sf,  rs))

#    for pr in bal.probes:
#        list.append(CreateProbeCommand(driver,  context,  pr))
#        list.append(AddProbeToSFCommand(driver,  context,  bal.sf,  pr))
    for vip in bal.vips:
        list.append(CreateVIPCommand(driver,  context,  vip,  bal.sf))
    return list


def makeDeleteLBCommandChain(bal,  driver,  context):
    list = []
    for vip in bal.vips:
        list.append(DeleteVIPCommand(driver,  context,   vip))
#    for pr in bal.probes:
#        list.append(DeleteProbeFromSFCommand(driver,  context,  bal.sf,  pr))
#        list.append(DeleteProbeCommand(driver,  context,  pr))
    for rs in bal.rs:
        list.append(DeleteRServerFromSFCommand(driver, context, bal.sf,  rs))
        list.append(DeleteRServerCommand(driver,  context, rs))
    for pr in bal.probes:
        list.append(DeleteProbeFromSFCommand(driver,  context,  bal.sf,  pr))
        list.append(DeleteProbeCommand(driver,  context,  pr))
    if  len(bal.sf._sticky) > 0:
        for st in bal.sf._sticky:
            list.append(DeleteStickyCommand(driver, context, st))
    list.append(DeleteServerFarmCommand(driver, context,  bal.sf))

    return list


def makeUpdateLBCommandChain(old_bal,  new_bal,  driver,  context):
    list = []
    if old_bal.lb.algorithm != new_bal.lb.algorithm:
        list.append(CreateServerFarmCommand(driver, context,  new_bal.sf))
    return list


def makeAddNodeToLBChain(bal, driver,  context,  rs):
    list = []
    list.append(CreateRServerCommand(driver, context, rs))
    list.append(AddRServerToSFCommand(driver, context, bal.sf, rs))
    return list


def makeDeleteNodeFromLBChain(bal, driver,  context,  rs):
    list = []
    list.append(DeleteRServerFromSFCommand(driver, context, bal.sf, rs))
    list.append(DeleteRServerCommand(driver, context, rs))
    return list


def makeAddProbeToLBChain(bal, driver, context,  probe):
    list = []
    list.append(CreateProbeCommand(driver, context, probe))
    list.append(AddProbeToSFCommand(driver, context, bal.sf, probe))
    return list


def makeDeleteProbeFromLBChain(bal, driver, context, probe):
    list = []
    list.append(DeleteProbeFromSFCommand(driver, context, bal.sf, probe))
    list.append(DeleteProbeCommand(driver, context, probe))
    return list

def makeAddStickyToLBChain(bal, driver, context, sticky):
    list = [CreateStickyCommand(driver, context, sticky)]
    return list


def makeDeleteStickyFromLBChain(bal, driver, context, sticky):
    list = [DeleteStickyCommand(driver, context, sticky)]
    return list


class Deployer(object):
    def __init__(self):
        self.commands = []

    def execute(self):
        for index in range(len(self.commands)):
            current_command = self.commands[index]
            try:
                current_command.execute()
            except openstack.common.exception.Invalid  as ex:
                i = index - 1
                logger.error("Got exception during deploy. \
                               Rolling back changes. Error message %s" % ex)

                for k in range(index - 1):
                    command = self.commands[i - k]
                    command.undo()
                raise openstack.common.exception.Error()

            except openstack.common.exception.Error  as ex:
                i = index - 1
                logger.error("Got exception during deploy. \
                               Rolling back changes. Error message %s" % ex)

                for k in range(index - 1):
                    command = self.commands[i - k]
                    command.undo()
                raise openstack.common.exception.Error()


class Destructor(object):
    def __init__(self):
        self.commands = []

    def execute(self):
        for index in range(len(self.commands)):
            current_command = self.commands[index]
            try:
                current_command.execute()
                logger.debug("Execute command: %s" % current_command)
            except:

                logger.error("Got exception during deleting.")
                #raise openstack.common.exception.Error()


class CreateRServerCommand(object):
    def __init__(self,  driver,  context,  rs):
        self._driver = driver
        self._context = context
        self._rs = rs

    def execute(self):
        # We can't create multiple RS with the same IP. So parent_id points to RS which already deployed and has this IP
        logger.debug("Creating rserver command execution with rserver: %s" % self._rs)
        logger.debug("RServer parent_id: %s" % self._rs.parent_id)
        if self._rs.parent_id == "":
            self._driver.createRServer(self._context,  self._rs)
            self._rs.deployed = 'True'
            stor = balancer.storage.storage.Storage()
            wr = stor.getWriter()
            wr.updateDeployed(self._rs,  'True')
            

    def undo(self):
        try:
            self._driver.deleteRServer(self._context,  self._rs)
            self._rs.deployed='False'
            stor = balancer.storage.storage.Storage()
            wr = stor.getWriter()
            wr.updateDeployed(self._rs,  'False')
        except:
            pass


class DeleteRServerCommand(object):
    def __init__(self,  driver,  context,  rs):
        self._driver = driver
        self._context = context
        self._rs = rs

    def execute(self):
        store = balancer.storage.storage.Storage()
        reader = store.getReader()
        if self._rs.parent_id != "" and balancer.common.utils.checkNone(self._rs.parent_id):
            # rs2
            rss = reader.getRServersByParentID(self._rs.parent_id)
            if len(rss) == 1:
                parent_rs = reader.getRServerById(self._rs.parent_id)
                self._driver.deleteRServer(self._context,   parent_rs)
        else:
            # rs1
            # We need to check if there are reals who reference this rs as a parent
            rss = reader.getRServersByParentID(self._rs.id)
            if len(rss) == 0:
                self._driver.deleteRServer(self._context,   self._rs)
            pass


class CreateStickyCommand(object):
    def __init__(self, driver,  context,  sticky):
        self._driver = driver
        self._context = context
        self._sticky = sticky
        
    def execute(self):
        self._driver.createStickiness(self._context,  self._sticky)
        self._sticky.deployed='True'
        stor = balancer.storage.storage.Storage()
        wr = stor.getWriter()
        wr.updateDeployed(self._sticky,  'True')


class DeleteStickyCommand(object):
    def __init__(self, driver,  context,  sticky):
        self._driver = driver
        self._context = context
        self._sticky = sticky
        
    def execute(self):
        self._driver.deleteStickiness(self._context,  self._sticky)
        self._sticky.deployed = 'False'
        stor = balancer.storage.storage.Storage()
        wr = stor.getWriter()
        wr.updateDeployed(self._sticky,  'False')


class CreateServerFarmCommand(object):
    def __init__(self,  driver,  context,  sf):
        self._driver = driver
        self._context = context
        self._sf = sf

    def execute(self):
        self._driver.createServerFarm(self._context,  self._sf)
        self._sf.deployed = 'True'
        stor = balancer.storage.storage.Storage()
        wr = stor.getWriter()
        wr.updateDeployed(self._sf,  'True')

    def undo(self):
        try:
            self._driver.deleteServerFarm(self._context,  self._sf)
            self._sf.deployed='False'
            stor = balancer.storage.storage.Storage()
            wr = stor.getWriter()
            wr.updateDeployed(self._sf,  'False')
        except:
            pass


class DeleteServerFarmCommand(object):
    def __init__(self,  driver,  context,  sf):
        self._driver = driver
        self._context = context
        self._sf = sf

    def execute(self):
        self._driver.deleteServerFarm(self._context,  self._sf)
        self._sf.deployed='False'
        stor = balancer.storage.storage.Storage()
        wr = stor.getWriter()
        wr.updateDeployed(self._sf,  'False')

class AddRServerToSFCommand(object):
    def __init__(self,  driver,  context,  sf, rs):
        self._driver = driver
        self._context = context
        self._sf = sf
        self._rs = rs

    def execute(self):
        if self._rs.parent_id != "":
            #Nasty hack. We need to think how todo this more elegant
            self._rs.name = self._rs.parent_id
            
        self._driver.addRServerToSF(self._context,  self._sf,  self._rs)

    def undo(self):
        try:
            self._driver.deleteRServerFromSF(self._context,  self._sf,  self._rs)
        except:
            pass


class DeleteRServerFromSFCommand(object):
    def __init__(self,  driver,  context,  sf, rs):
        self._driver = driver
        self._context = context
        self._sf = sf
        self._rs = rs

    def execute(self):
        self._driver.deleteRServerFromSF(self._context,  self._sf,  self._rs)


class CreateProbeCommand(object):
    def __init__(self,  driver,  context,  probe):
        self._driver = driver
        self._context = context
        self._probe = probe

    def execute(self):
        self._driver.createProbe(self._context, self._probe)
        self._probe.deployed='True'
        stor = balancer.storage.storage.Storage()
        wr = stor.getWriter()
        wr.updateDeployed(self._probe,  'True')

    def undo(self):
        try:
            self._driver.deleteProbe(self._context, self._probe)
            self._probe.deployed='False'
            stor = balancer.storage.storage.Storage()
            wr = stor.getWriter()
            wr.updateDeployed(self._probe,  'False')           
        except:
            pass


class DeleteProbeCommand(object):
    def __init__(self,  driver,  context,  probe):
        self._driver = driver
        self._context = context
        self._probe = probe

    def execute(self):
        self._driver.deleteProbe(self._context, self._probe)
        self._probe.deployed='False'
        stor = balancer.storage.storage.Storage()
        wr = stor.getWriter()
        wr.updateDeployed(self._probe,  'False')


class AddProbeToSFCommand(object):
    def __init__(self,  driver,  context,  sf,  probe):
        self._driver = driver
        self._context = context
        self._probe = probe
        self._sf = sf

    def execute(self):
        self._driver.addProbeToSF(self._context,  self._sf,  self._probe)

    def undo(self):
        try:
            self._driver.deleteProbeFromSF(self._context,  self._sf,  self._probe)
        except:
            pass


class DeleteProbeFromSFCommand(object):
    def __init__(self,  driver,  context,  sf,  probe):
        self._driver = driver
        self._context = context
        self._probe = probe
        self._sf = sf

    def execute(self):
        self._driver.deleteProbeFromSF(self._context,  self._sf,  self._probe)
        
class ActivateRServerCommand(object):
    def __init__(self,  driver,  context,  sf,  rs):
        self._driver = driver
        self._context = context
        self._rs = rs
        self._sf = sf

    def execute(self):
        self._driver.activateRServer(self._context,  self._sf,  self._rs)

class SuspendRServerCommand(object):
    def __init__(self,  driver,  context,  sf,  rs):
        self._driver = driver
        self._context = context
        self._rs = rs
        self._sf = sf

    def execute(self):
        self._driver.suspendRServer(self._context,  self._sf,  self._rs)



class CreateVIPCommand(object):
    def __init__(self,  driver,  context,  vip,  sf):
        self._driver = driver
        self._context = context
        self._vip = vip
        self._sf = sf

    def execute(self):
        self._driver.createVIP(self._context,  self._vip,  self._sf)
        self._vip.deployed='True'
        stor = balancer.storage.storage.Storage()
        wr = stor.getWriter()
        wr.updateDeployed(self._vip,  'True')

    def undo(self):
        try:
            self._driver.deleteVIP(self._context,  self._vip,  self._sf)
            self._vip.deployed='False'
            stor = balancer.storage.storage.Storage()
            wr = stor.getWriter()
            wr.updateDeployed(self._vip,  'False')
        except:
            pass


class DeleteVIPCommand(object):
    def __init__(self,  driver,  context,  vip):
        self._driver = driver
        self._context = context
        self._vip = vip

    def execute(self):
        self._driver.deleteVIP(self._context,   self._vip)
        self._vip.deployed='False'
        stor = balancer.storage.storage.Storage()
        wr = stor.getWriter()
        wr.updateDeployed(self._vip,  'False')


def createProbe(probe_type):
    probeDict = {'DNS': probe.DNSprobe(), 'ECHO TCP': probe.ECHOTCPprobe(),
                'ECHO UDP': probe.ECHOUDPprobe(), 'FINGER': probe.FINGERprobe(),
                'FTP': probe.FTPprobe(), 'HTTPS': probe.HTTPSprobe(),
                'HTTP': probe.HTTPprobe(), 'ICMP': probe.ICMPprobe(),
                'IMAP': probe.IMAPprobe(), 'POP': probe.POPprobe(),
                'RADIUS': probe.RADIUSprobe(), 'RTSP': probe.RTSPprobe(),
                'SCRIPTED': probe.SCRIPTEDprobe(),
                'SIP TCP': probe.SIPTCPprobe(),
                'SIP UDP': probe.SIPUDPprobe(), 'SMTP': probe.SMTPprobe(),
                'SNMP': probe.SNMPprobe(), 'CONNECT': probe.TCPprobe(),
                'TELNET': probe.TELNETprobe(), 'UDP': probe.UDPprobe(),
                'VM': probe.VMprobe()}
    obj = probeDict.get(probe_type,  None)
    if obj == None:
        raise openstack.common.exception.Invalid("Can't create health \
			   monitoring probe of type %s" % probe_type)
    return obj.createSame()


def createPredictor(pr_type):
    predictDict = {'HashAddr': predictor.HashAddrPredictor(),
                  'HashContent': predictor.HashContent(),
                  'HashCookie': predictor.HashCookie(),
                  'HashHeader': predictor.HashHeader(),
                  'HashLayer4': predictor.HashLayer4(),
                  'HashURL': predictor.HashURL(),
                  'LeastBandwidth': predictor.LeastBandwidth(),
                  'LeastConnections': predictor.LeastConn(),
                  'LeastLoaded': predictor.LeastLoaded(),
                  'Response': predictor.Response(),
                  'RoundRobin': predictor.RoundRobin()}

    obj = predictDict.get(pr_type,  None)
    if obj == None:
        raise openstack.common.exception.Invalid("Can't find load balancing \
                                           algorithm with type %s" % pr_type)
    return obj.createSame()


def createSticky(st_type):
    stickyDict = {'http-content': sticky.HTTPContentSticky(), \
                        'http-cookie': sticky.HTTPCookieSticky(), \
                        'http-header': sticky.HTTPHeaderSticky(), \
                        'ip-netmask': sticky.IPNetmaskSticky(), \
                        'layer4-payload': sticky.L4PayloadSticky(), \
                        'rtsp-header': sticky.RTSPHeaderSticky(), \
                        'radius': sticky.RadiusSticky(), \
                        'sip-header': sticky.SIPHeaderSticky(), \
                        'v6prefix': sticky.v6PrefixSticky()}

    obj = stickyDict.get(st_type,  None)
    if obj == None:
        raise openstack.common.exception.Invalid("Can't find load balancing \
                                           algorithm with type %s" % st_type)
    return obj.createSame()
