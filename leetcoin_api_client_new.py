
# Import Python Modules
import threading, Queue, time, sys, traceback
import es
import re
import md5
import playerlib
import repeat
import urllib
import httplib
import time
import datetime
import hashlib
import hmac
import math
import gamethread
from ordereddict import OrderedDict

try: import simplejson as json
except ImportError: print ("Json Import Error")

# Import Config
from config import *

#global variables required for thread synchronization
actionQueue = queue.Queue(25) # available queue options:
'''
request award
activate player
deactivate plaery
submit match results
'''
_REQUEST_AWARD = 0
_ACTIVATE_PLAYER = 1
_DEACTIVATE_PLAYER = 2
_SUBMIT_MATCH_RESULTS = 3
'''
    data coming into the queue is in the following format:
    [ <0|1|2|3> , {#all action args as a dictionary#} ]
    so, we have a list. first item is one of 0, 1, 2, or 3.
    second item is a dictionary with each itemof "arg variable" : "arg value"
'''

sharedDataSemaphore = threading.Semaphore(1)
esModuleSemaphore = threading.Semaphore(1)
'''
in the previous model, the threads were all over the place, some were proper thread classes,
whereas others were simple targets for threading to use.
in this new model, we will have one worker/consumer class and one leetcoinapiclient/producer
class. the producer will produce items into the Queue to do certain methods (ie activate,
deactivate, submit results...etc)
the consumers will simply take whatever is available and act upon what it is told.
'''





class SharedData():
    def __init__(self, url, api_key, shared_secret, encryption, debug, 
        self.authorizedPlayerObjectList = []
        self.players_connected = False

    def add_to_authorized_player_list(self, player_obj):
        self.authorizedPlayerObjectList.append(player_obj)

    def get_authorized_player_list(self):
        return self.authorizedPlayerObjectList

    def len_authorized_player_list(self):
        return len(self.authorizedPlayerObjectList)

    def delete_from_authorized_player_list(self, index)
        self.authorizedPlayerObjectList.pop(index)

    def set_players_connected(self, value):
        self.players_connected = value

    def get_players_connected(self):
        return self.players_connected

class Award():
    """ a leetcoin award """
    def __init__(self, playerKey, playerUserId, playerName, amount, title):
        self.playerKey = playerKey
        self.playerUserId = playerUserId
        self.playerName = playerName
        self.amount = amount
        self.title = title
    def to_dict(self):
        return ({
            u'playerKey': self.playerKey,
            u'playerUserId': self.playerUserId,
            u'playerName': self.playerName,
            u'amount': self.amount,
            u'title': self.title
        })

class Player():
    """ a leetcoin player """
    def __init__(self, key, platformID, btcBalance, btcHold, kills, deaths, player_active, name, userid=0, rank=1600):
        self.key = key
        self.platformID = platformID
        self.btcBalance = btcBalance
        self.btcHold = btcHold
        self.kills = kills
        self.deaths = deaths
        self.player_active = player_active
        self.name = name
        self.disconnected = False
        self.userid = userid
        self.rank = rank
        self.kick = False
        self.weapon = ""
        self.activate_timestamp = datetime.datetime.now()
        self.deactivate_timestamp = datetime.datetime.now()
    
    def activate(self, userid, satoshi_balance):
        self.player_active = True
        self.userid = userid
        self.btcBalance = satoshi_balance
        self.btcHold = satoshi_balance
        
    def deactivate(self):
        self.player_active = False
        
    def to_dict(self):
        return ({
                u'key': self.key,
                u'platformID': self.platformID,
                u'btcBalance': self.btcBalance,
                u'btcHold': self.btcHold,
                u'kills': self.kills,
                u'deaths': self.deaths,
                u'player_active': self.player_active,
                u'name': self.name,
                u'rank': self.rank,
                u'weapon': self.weapon
                })

class LeetCoinAPIClient():

    def __init__(self, url, api_key, shared_secret, encryption, debug=True):
        self.url = url
        self.api_key = api_key
        self.shared_secret = shared_secret
        self.encryption = encryption
        self.debug = debug
        self.players_connected = False # track if players are still connected


        self.shareddata = SharedData()
        max_threads = 5
        # start up the threads.
        self.workers = []
        for i in range(0, max_threads):
            self.workers.append(Workers(i, self.shareddata, debug)
        for i in self.workers:
            i.start()
        
        self.totalkills = 0 # track total kills for server
        self.matchkills = 0 # kills for this batched round

        self.active_players_changed = False

        self.refresh_authorized_players = False

        self.last_get_server_info = datetime.datetime.now()

        server_info_json = self.getServerInfo()
        server_info = json.loads(server_info_json)
        
        if 'serverRakeBTCPercentage' in server_info:

            self.serverRakeBTCPercentage = float(server_info['serverRakeBTCPercentage'])
            self.leetcoinRakePercentage = float(server_info['leetcoinRakePercentage'])
            self.incrementBTC = int(server_info['incrementBTC'])
            ## calculate and store attacker reward per kill for use later
            total_rake = self.serverRakeBTCPercentage + self.leetcoinRakePercentage
            self.kill_reward = int(math.ceil(self.incrementBTC - (self.incrementBTC * total_rake)))
        
            self.no_death_penalty = server_info['no_death_penalty']
            self.allow_non_authorized_players = server_info['allow_non_authorized_players']
        
            self.authorizedPlayerObjectList = []
            
            #self.awardQueue = []
            
            self.minumumBTCHold = server_info['minimumBTCHold']
        
            log_file = open('error_logs.txt', 'a') 
            log_file.write('-------- LEETCOIN API CLIENT INIT -----------\n')
            log_file.write('%s\n' %datetime.datetime.now())
            log_file.close()

            if self.debug:
                print("----------------------- SERVER INIT ------------------------")
                print("[1337] serverRakeBTCPercentage: %s" %self.serverRakeBTCPercentage)
                print("[1337] leetcoinRakePercentage: %s" %self.leetcoinRakePercentage)
                print("[1337] incrementBTC: %s" %self.incrementBTC)
                print("[1337] kill_reward: %s" %self.kill_reward)

                print("[1337] minumumBTCHold: %s" %self.minumumBTCHold)
        else:
            print("[1337] ERROR ACCESSING SERVER INFO - BE SURE API KEY AND SECRET ARE SET CORRECTLY " )

    def repeatingServerUpdate(self):
        ''' repeating server callw hich performs several tasks in sequence '''
        if self.debug:
            print("--------------------- SERVER UPDATE --------------------------")
        # TODO put a SUBMIT MATCH RESULTS on the queue
        global actionQueue
        new_dict = {}
        sharedDataSemaphore.acquire()
        sharedDataSemaphore.release()
        new_dict["match_kills"] = self.matchkills
        actionQueue.put([_SUBMIT_MATCH_RESULTS, new_dict])
#        thread1 = ThreadedSubmitMatchResults(1, "submitMatchResults", 
#                                                self,
#                                                self.players_connected,
#                                                self.matchkills,
#                                                self.authorizedPlayerObjectList,
#                                                self.active_players_changed,
#                                                self.encryption, 
#                                                self.debug)
#
        
    def notifyRefreshAuthorizedPlayers(self):
        ''' i have no idea what this does'''
        self.refresh_authorized_players = True
    def notifyActivePlayersChanged(self):
        ''' i have no idea what this does'''
        self.active_players_changed = True

    def recordKill(self, victim_64, attacker_id):
        ''' add a kill to the kill record '''
        if self.debug:
            print("[1337] [recordKill] recording kill. %s killed %s" % (attacker_id, victim_64))
            print("[1337] [recordKill] kill reward: %s" % self.kill_reward)
            print("[1337] [recordKill] increment btc: %s" % self.incrementBTC)
        v_index, victim = self.getPlayerObjByPlatformID(victim_64)
        a_index, attacker = self.getPlayerObjByUserid(attacker_id)
        kick_player = False
        attacker_player = playerlib.getPlayer(attacker_id)
        if self.debug:
            print("[1337] [recordKill] Victim Index: %s" % v_index)
            print("[1337] [recordKill] Victim ID: %s" % id(victim))
            print("[1337] [recordKill] Attacker Index: %s" % a_index)
            print("[1337] [recordKill] Attacker ID: %s" % id(attacker))
        if victim and attacker:
            # prevent suicide from counting
            if id(attacker) != id(victim): 
                attacker.btcBalance = attacker.btcBalance + self.kill_reward
                if not self.no_death_penalty:
                    victim.btcBalance = victim.btcBalance - self.incrementBTC
                victim.deaths = victim.deaths +1
                attacker.kills = attacker.kills +1
                attacker.weapon = attacker_player.weapon
                ## get new ranking
                new_winner_rank, new_loser_rank  = self.calculate_elo_rank(player_a_rank=attacker.rank ,player_b_rank=victim.rank )
                victim.rank = int(new_loser_rank)
                attacker.rank = int(new_winner_rank)
                if victim.btcBalance < self.minumumBTCHold:
                    kick_player = True
                    victim.kick = True
                    self.deactivatePlayer(victim_64, kick=True, message="Your balance is too low to continue playing.  Go to leetcoin.com to add more btc to your server hold.")
                self.matchkills = self.matchkills +1
                tell_all_players('%s earned: %s Satoshi for killing %s'
                                % (attacker.name, self.kill_reward, victim.name))
            return kick_player, victim.btcBalance, attacker.btcBalance
        else:
            print("[1337] [recordKill] ERROR - Victim or attacker player object not found")
            tell_all_players('Non-Authorized player kill/death.  Authorize this server on www.leetcoin.com for tracking, and rewards!')
            return True, 0, 0


    def authorizeActivatePlayer(self, steam_64, userid):
        ''' activate a player by putting their information in the QUEUE '''
        global actionQueue
        if self.debug:
            print ("[1337] [authorizeActivatePlayer]")
        # TODO put somethin gon the queue
        new_dict = {}
        new_dict["userid"] = userid
        actionQueue.put([_ACTIVATE_PLAYER, new_dict])

    def deactivatePlayer(self, steam_64, kick=False, message="You have been kicked from the server.  Go to leetcoin.com to verify your balance and authorization status."):
        global actionQueue
        if self.debug:
            print ("[1337] deactivatePlayer")
        #thread = ThreadedDeactivatePlayer(steam_64,  self, self.encryption, self.debug, kick, message)
        new_dict = {}
        new_dict["platformid"] = steam_64
        new_dict["encryption"] = self.encryption
        new_dict["kick"] = kick
        new_dict["message"] = message
        actionQueue.put([_DEACTIVATE_PLAYER, new_dict])
        # TODO put something on the queue

    def getServerInfo(self):
        if self.debug:
            print("[1337] getServerInfo")
        uri = "/api/get_server_info"
        self.last_get_server_info = datetime.datetime.now()
        params = OrderedDict([
                    ("encryption", self.encryption),
                    ("nonce", time.time() ),
                     ])
        response = self._get_https_response(params, uri)
        return response

    def getPlayerBalance(self, steam_64):
        """ Get player's balance """
        index, player_obj = self.getPlayerObjByPlatformID(steam_64)
        if self.debug:
            print ("[1337] getPlayerBalance for platformID %s" %steam_64)
            print ("[1337] getPlayerBalance for index %s" %index)
        if player_obj:
            return "Your Server Balance is %1.8f BTC, (%s Satoshi)" %(float(player_obj.btcBalance)/100000000., player_obj.btcBalance)
        else:
            return "Your balance is currently being updated.  Stand by."

    def getPlayerRank(self, steam_64):
        """ Get player's rank """
        index, player_obj = self.getPlayerObjByPlatformID(steam_64)
        if self.debug:
            print ("[1337] getPlayerRank for platformID %s" %steam_64)
            print ("[1337] getPlayerRank for index %s" %index)
        if player_obj:
            return "Rank score: %s" %player_obj.rank
        else:
            return "Your rank is currently being updated.  Stand by."

    def getPlayerObjByPlatformID(self, steam_64):
        """ get a player object from a platform ID """
        if self.debug:
            print ("[1337] [getPlayerObjByPlatformID]")
        player_found = False
        sharedDataSemaphore.acquire()
        authorizedPlayers = self.shareddata.get_authorized_player_list()
        for index, player_obj in enumerate(authorizedPlayers): #this needs semaphore control
            if player_obj.platformID == steam_64:
                player_found = True
                player_index = index
                player_object = player_obj
                break
        if player_found:
            if self.debug:
                print("[1337] [getPlayerObjByPlatformID] Player Found!")
                print("[1337] [getPlayerObjByPlatformID] player_index: %s" % player_index)
                print("[1337] [getPlayerObjByPlatformID] player_object: %s" % player_object)
            sharedDataSemaphore.release()
            return player_index, player_object
        else:
            if self.debug:
                print("[1337] [getPlayerObjByPlatformID] [ERROR] Player NOT Found!")
            sharedDataSemaphore.release()
            return None, None
        sharedDataSemaphore.release()

    def getPlayerObjByKey(self, key):
        """ get a player object from a key """
        if self.debug:
            print ("[1337] [getPlayerObjByKey]")
        player_found = False
        sharedDataSemaphore.acquire()
        authorizedPlayers = self.shareddata.get_authorized_player_list()
        for index, player_obj in enumerate(authorizedPlayers):
            if player_obj.key == key:
                player_found = True
                player_index = index
                player_object = player_obj
        if player_found:
            if self.debug:
                print ("[1337] [getPlayerObjByKey] Player Found!")
                print ("[1337] [getPlayerObjByKey] player_index: %s" %player_index)
                print ("[1337] [getPlayerObjByKey] player_object: %s" %player_object)
            sharedDataSemaphore.release()
            return player_index, player_object
        else:
            if self.debug:
                print ("[1337] [getPlayerObjByKey] Player NOT Found!")
            sharedDataSemaphore.release()
            return None, None
        sharedDataSemaphore.release()

    def getPlayerObjByUserid(self, userid):
        """ get a player object from a userid """
        if self.debug:
            print ("[1337] [getPlayerObjByUserid]")
        player_found = False
        sharedDataSemaphore.acquire()
        authorizedPlayers = self.shareddata.get_authorized_player_list()
        for index, player_obj in enumerate(authorizedPlayers):
            if player_obj.userid == userid:
                player_found = True
                player_index = index
                player_object = player_obj
        if player_found:
            if self.debug:
                print ("[1337] [getPlayerObjByUserid] Player Found!")
                print ("[1337] [getPlayerObjByUserid] player_index: %s" %player_index)
                print ("[1337] [getPlayerObjByUserid] player_object: %s" %player_object)
            sharedDataSemaphore.release()
            return player_index, player_object
        else:
            if self.debug:
                print ("[1337] [getPlayerObjByUserid] Player NOT Found!")
            sharedDataSemaphore.release()
            return None, None
        sharedDataSemaphore.release()

    def requestAward(self, amount, title, player):
        if self.debug:
            print ("[1337] [requestAward]")
            print ("[1337] [requestAward] amount: %s" %amount)
            print ("[1337] [requestAward] title: %s" %title)
            print ("[1337] [requestAward] player: %s " %player)
        ## Make sure there is more than 1 player active.
        count = self.get_active_player_count()
        if count < 2:
            print("CANNOT ISSUE AN AWARD - LESS THAN TWO PLAYERS ONLINE")
            return False
        player_index, player_obj = self.getPlayerObjByUserid(player)
        if not player_obj:
            print("CANNOT ISSUE AN AWARD - COULD NOT GET PLAYER")
            return False
        award = Award(player_obj.key, player_obj.userid, player_obj.name, amount, title)
        # TODO put something on the queue
        global actionQueue
        new_dict = {}
        new_dict["award"] = award
        new_dict["encryption"] = "md5"
        actionQueue.put([_REQUEST_AWARD, new_dict])

        #thread = threading.Thread(target=ThreadedRequestAward, args=(award, "md5", self))
        
    def calculate_elo_rank(self, player_a_rank=1600, player_b_rank=1600, penalize_loser=True):
        winner_rank, loser_rank = player_a_rank, player_b_rank
        rank_diff = winner_rank - loser_rank
        exp = (rank_diff * -1) / 400
        odds = 1 / (1 + math.pow(10, exp))
        if winner_rank < 2100:
            k = 32
        elif winner_rank >= 2100 and winner_rank < 2400:
            k = 24
        else:
            k = 16
        new_winner_rank = round(winner_rank + (k * (1 - odds)))
        if penalize_loser:
            new_rank_diff = new_winner_rank - winner_rank
            new_loser_rank = loser_rank - new_rank_diff
        else:
            new_loser_rank = loser_rank
        if new_loser_rank < 1:
            new_loser_rank = 1
        return (new_winner_rank, new_loser_rank)
        









class Worker(threading.Thread):
    '''
        this thread class is a worker thread, It gets a recent item from the queue
        and does whatever work is requested on the queue.
    ''' 

    def __init__(self, threadID, shareddata, debug):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.shareddata = shareddata
        self.debug = debug

    def getPlayerObjByUserid(self, userid, debug):
        ''' get a player object from a userid '''
        if debug:
            print ("[1337] [%s] [getPlayerObjByUserid]" % self.threadID)
        player_found = False
        sharedDataSemaphore.acquire()
        authorizedPlayers = self.shareddata.get_authorized_player_list()
        for index, player_obj in enumerate(authorizedPlayers) #######!!!!!!!!!! <- this is shared data!
            if player_obj.userid == userid:
                player_found = True
                player_index = index
                player_object = player_obj
                break
        if player_found:
            if debug:
                print("[1337] [%s] [getPlayerObjByUserid] Player Found!")
                print("[1337] [%s] [getPlayerObjByUserid] player_index: %s" % player_index)
                print("[1337] [%s] [getPlayerObjByUserid] player_object: %s" % player_object)
            sharedDataSemaphore.release()
            return player_index, player_object
        else:
            if debug:
                print("[1337] [%s] [getPlayerObjByUserid] player NOT found!")
            sharedDataSemaphore.release()
            return None, None
        sharedDataSemaphore.release()



    def get_https_response(self, params, uri, debug):
        ''' perform the https post conenction and return results'''
        if debug:
            print ("[1337] [%s] get_https_response %s" % (self.threadID, uri))
        params = urllib.urlencode(params)
        H = md5.new(shared_secret)
        H.update(params)
        sign = H.hexdigest()
        headers = { "Content-type": "application/x-www-form-urlencoded", "Key":api_key, "Sign":sign }
        conn = httplib.HTTPConnection(url)
        conn.request("POST", uri, params, headers)
        response = conn.getresponse()
        return response.read()

    def doKick(userid, message, first_attempt):
        esModuleSemaphore.acquire()
        es.server.queuecmd("kickid %s Reason: %s" % (userid, message))
        esModuleSemaphore.release()

    def activate_player(self, action_args):
        if self.debug:
            print("[1337] [%s] [activate_player] activating player" % (self.threadID))
        userid = action_args["userid"]
        uri = "/api/activate_player"
        params = OrderedDict([
            ("encryption", self.encryption),
            ("nonce", time.time() ),
            ("platformid", self.platformid),
        ])
        response = self.get_https_response(params, uri, self.debug)
        player_info = json.loads(response)
        #self.apiClient.threadActivatePlayer(self.userid, player_info)
        if self.debug:
            print("[1337] [%s] [threadActivatePlayer]" % (self.threadID))
            print("[1337] [%s] [threadActivatePlayer] player_info: %s" % (self.threadID, player_info))
            print("[1337] [%s] [threadActivatePlayer] userid: %s" % (self.threadID, userid))
        if player_info['player_authorized']:
            if self.debug:
                print("[1337] [%s] [threadActivatePlayer] Player authorized." % (self.threadID))
            btc_hold = int(player_info['player_btchold'])
            if btc_hold >= self.minumumBTCHold:
                if self.debug:
                    print ("[1337] [%s] [threadActivatePlayer] Balance >= minumum" % (self.threadID))
                index, player_obj = self.getPlayerObjByPlatformID(player_info['player_platformid'])
                ####3self.players_connected = True
                sharedDataSemaphore.acquire()
                self.shareddata.set_players_connected(True)
                sharedDataSemaphore.release()
                if player_obj:
                    if self.debug:
                        print ("[1337] [%s] [authorizeActivatePlayer] Player Obj found in player obj list"
                               % (self.threadID))
                    player_obj.btcBalance = player_info['player_btchold']
                    player_obj.btcHold = player_info['player_btchold']
                    player_obj.rank = player_info['player_rank']
                    player_obj.kills = 0
                    player_obj.deaths = 0
                    player_obj.player_active = True
                    player_obj.disconnected = False
                    player_obj.userid = userid
                else:
                    if self.debug:
                        print ("[1337] [%s] [authorizeActivatePlayer] Player Obj NOT found "
                                "in player obj list - adding" % (self.threadID))
                    player_rank = int(player_info['player_rank'])
                    player_obj = Player(player_info['player_key'], 
                                        player_info['player_platformid'],
                                        player_info['player_btchold'],
                                        player_info['player_btchold'],
                                        0, 
                                        0, 
                                        True, 
                                        player_info['player_name'],
                                        userid=userid, 
                                        rank=player_rank)
                    sharedDataSemaphore.acquire()
                    self.shareddata.add_to_authorized_player_list(player_obj)
#                    self.authorizedPlayerObjectList.append(player_obj) ## TODO GLOBAL VAR!!!
                    sharedDataSemaphore.release()
            else:
                # player does NOT have enough balance to play
                if self.debug:
                    print ("[1337] [%s] [activate player] Player balance too low." % self.threadID)
                self.doKick(userid, "Your balance is too low to play on this server.  Go to leetcoin.com to add more to your balance.", True)
                global actionQueue
                new_dict = {}
                new_dict["platformid"] = player_info["player_platformid"]
                new_dict["encryption"] = self.encryption
                new_dict["kick"] = False
                new_dict["message"] = "Balance too low to play!"
                actionQueue.put([_DEACTIVATE_PLAYER, new_dict])
                ## TODO PUT SOMETHING ON THE QUEUE FOR DEACTIVATING A PLAYER
        else:
            # player is NOT authorized.
            if self.debug:
                print("[1337] [%s] [activate player] player NOT authorized" % self.threadID)
            if allow_non_authorized_players:
                if debug:
                    print("[1337] [%s] [activate player] non authorized players are permitted")
            else:
                self.doKick(userid, "this server is nto authorized for you. go to leetcoin.com to authorize it", True)
                ## TODO PUT SOMETHING ON THE QUEUE FOR DEACTIVATING A PLAYER
                global actionQueue
                new_dict = {}
                new_dict["platformid"] = player_info["player_platformid"]
                new_dict["encryption"] = self.encryption
                new_dict["kick"] = False
                new_dict["message"] = "Not Authorized"
                actionQueue.put([_DEACTIVATE_PLAYER, new_dict])
                #thread = ThreadedDeactivatePlayer(player_info['player_platformid'], self, self.encryption, self.debug, False, "not authorized")

    def deactivate_player(self, action_args):
        platformid = action_args["platformid"]
        encryption = action_args["encryption"]
        kick = action_args["kick"]
        message = action_args["message"]

        if self.debug:
            print("[1337] [%s DeactivatePlayer]" % self.threadID)
        uri = "/api/deactivate_player"
        params = OrderedDict([
            ("encryption", encryption),
            ("nonce", time.time()),
            ("platformid", platformid),
            ])
        response = self.get_https_response(params, uri)
        player_info = json.loads(response)
        index, player_obj = self.getPlayerObjByKey(player_info['player_key'])
        self.doKick(player_obj.userid, message, True)


    def request_award(self, action_args):
        uri = "/api/issue_award"
        debug = action_args["debug"]
        award = action_args["award"]
        encryption = action_args["encryption"]
        award_json = json.dumps(award.to_dict())

        params = OrderedDict([
                ("award", award_json),
                ("encryption", encryption),
                ("nonce", time.time()),
            ])
        response = self.get_https_response(params, uri, False)
        award_info = json.loads(response)
        if self.debug:
            print ("[1337] [%s] [request_award]" % self.threadID)
            print ("[1337] [%s] [request_award] award_info: %s" % (self.threadID, award_info))
            print ("[1337] [%s] [request_award] award: %s" % (self.threadID, award))
        if award_info("authorization"]:
            if award_info['award_authorized'] is True:
                if self.debug:
                    print("[1337] [%s] [request_award] AUTHORIZED!" % (self.threadID))
                    print("[1337] [%s] [request_award] award[playerKey]: %s" % (self.threadID, award.playerKey))
                    print("[1337] [%s] [request_award] award[playerUserId]: %s" % (self.threadID, award.playerUserId))
                    print("[1337] [%s] [request_award] award[amount]: %s" % (self.threadID, award.amount))
                    print("[1337] [%s] [request_award] award[title]: %s" % (self.threadID, award.title))
                player_index, player_obj = self.getPlayerObjByUserid(award.playerUserId, debug)
                if player_obj:
                    if self.debug:
                        print("[1337] [%s] [request_award] old balance: %s" % (self.threadID, player_obj.btcBalance))
                    player_obj.btcBalance = player_obj.btcBalance + int(award.amount)
                    if self.debug:
                        print("[1337] [%s] [request_award] new balance: %s" % (self.threadID, player.obj.btcBalance))
                    #tell_all_players('%s earned: %s Satoshi for: %s' %(player_obj.name, award.amount, award.title))
                    tell_all_players('%s earned: %s Satoshi for: %s'
                                      % (player_obj.name, award.amount, award.title))
                                      
                    
#        apiClient.threadRequestAward(award_info, award )

    def submit_match_results(self, action_args):
        debug = action_args["debug"]
        match_kills = action_args["match_kills"]


        if debug:
            print("[1337] [%s] [ThreadedSubmitMatchResults] run" % (self.threadID))
        sharedDataSemaphore.acquire()
        players_connected = self.shareddata.get_players_connected()
        sharedDataSemaphore.release()
        if players_connected:
            if debug:
                print("[1337] [%s] [ThreadedSubmitMatchResults] Players Connected" % (self.threadID))
            if match_kills > 0:
                if debug:
                    print("[1337] [%s] [ThreadedSubmitMatchResults] matchKills > 0" % (self.threadID))
                player_dict_list = []
                sharedDataSemaphore.acquire()
                authorizedPlayers = self.shareddata.get_authorized_player_list()
                for index, player_obj in enumerate(authorizedPlayers): ########!!!!!!! TODO GLOBAL VAR
                    player_dict_list.append(player_obj.to_dict())
                    # reset
                    player_obj.kills = 0
                    player_obj.deaths = 0
                    # deactivate if disconnected
                    if player_obj.disconnected or player_obj.kick:
                        ## remove the player from the apiClient object list
                        #self.apiClient.removePlayer(player_obj.platformID)
                        
                        active_players_changed = True
                        shareddata_len = self.shareddata.len_authorized_player_list()
                        if debug:
                            print("[1337] [%s] authorizedPlayerObjectList NEW size: %s" 
                                  % (self.threadID, shareddata_len))
                        if shareddata_len < 1: #####!!!! TODO GLOBAL VAR
                            if debug:
                                print("[1337] [%s] setting players_connected to False" % (self.threadID))
                            #self.apiClient.players_connected = False  <- TODO global var!!!
                            self.shareddata.set_players_connected(False)
                sharedDataSemaphore.release()
                self.apiClient.matchkills = 0

                if debug:
                    print("[1337] [%s] player_dict_list: %s" % (self.threadID, player_dict_list))
                uri = "/api/put_match_results"

                player_json_list = json.dumps(player_dict_list)
                params = OrderedDict([
                                  ("encryption", self.encryption),
                                  ("map_title", "Unknown"),
                                  ("nonce", time.time()),
                                  ("player_dict_list", player_json_list),
                                  ])
                

                response_json = self.get_https_response(params, uri, self.debug)
                response_obj = json.loads(response_json)
                if len(response_obj['playersToKick']) > 0:
                    if self.debug:
                        print("[1337] [%s] GOT playersToKick results from API" % (self.threadID))
                    player_keys = response_obj['playersToKick']
                    #self.apiClient.threadKickPlayersByKey(player_keys, "you were kicked by the leetcoin api" ### TODO

                if debug:
                    print("[1337] [%s] response_json: %s" % (self.threadID, response_json))

                return response_json
            else:
                if self.debug:
                    print("[1337] [%s] No Kills - Skipping" % (self.threadID))
                return False
        else:
            if self.debug:
                print("[1337] [%s] No Players - Skipping" % (self.threadID))
            return False





                        



    
    def run(self):
        global queue
        while True:
            print "%s waiting" % self.threadID
            indata = queue.get()
            action = indata[0]
            action_args = indata[1]
            if action == _ACTIVATE_PLAYER:
                self.activate_player(action_args)
            elif action == _DEACTIVATE_PLAYER:
                self.deactivate_player(action_args)
            elif action == _REQUEST_AWARD:
                self.request_award(action_args)
            elif action == _SUBMIT_MATCH_RESULTS:
                self.submit_match_results(action_args)

        






 
def tell_all_players(message):
    myPlayerList = playerlib.getPlayerList()
    for ply in myPlayerList:
        es.tell(ply.userid, message)
       
