## Interface to the leetcoin.com game server api
## For use with python eventscripts
## Version 0.0.2

## Install notes.  You will need to place simplejson in the python site_libs folder

# Import Python Modules
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
import threading
import gamethread
from ordereddict import OrderedDict

try: import simplejson as json
except ImportError: print ("Json Import Error")

# Import Config
from config import *

# threading stuff
threadLock = threading.Lock()
threads = []

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
    """ Client access to the leetcoin api """

    def __init__(self, url, api_key, shared_secret, encryption, debug=True):
        self.url = url
        self.api_key = api_key
        self.shared_secret = shared_secret
        self.encryption = encryption
        self.debug = debug
        self.players_connected = False # track if players are still connected
        
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
        """ repeating server call which performs several tasks in sequence """
        if self.debug:
            print("--------------------- SERVER UPDATE --------------------------")

        thread1 = ThreadedSubmitMatchResults(1, "submitMatchResults", 
                                                self,
                                                self.players_connected,
                                                self.matchkills,
                                                self.authorizedPlayerObjectList,
                                                self.active_players_changed,
                                                self.encryption, 
                                                self.debug)

        # Start new Threads
        thread1.start()
        threads.append(thread1)

    def notifyRefreshAuthorizedPlayers(self):
        self.refresh_authorized_players = True

    def notifyActivePlayersChanged(self):
        self.active_players_changed = True

    def recordKill(self, victim_64, attacker_id):
        """ Add a kill to the kill record """
        if self.debug:
            print("[1337] [recordKill] Recording kill.  %s killed %s" %(attacker_id, victim_64))
            print("[1337] [recordKill] kill reward: %s" %self.kill_reward)
            print("[1337] [recordKill] increment btc: %s" %self.incrementBTC)
            
        v_index, victim = self.getPlayerObjByPlatformID(victim_64)
        
        a_index, attacker = self.getPlayerObjByUserid(attacker_id)
        #a_index, attacker = self.getPlayerObjByPlatformID(attacker_64)
        kick_player = False
        
        attacker_player = playerlib.getPlayer(attacker_id)
        
        if self.debug:
            print("[1337] [recordKill] Victim Index: %s" %v_index)
            print("[1337] [recordKill] Victim ID: %s" %id(victim))
            print("[1337] [recordKill] Attacker Index: %s" %a_index)
            print("[1337] [recordKill] Attacker ID: %s" %id(attacker))
            
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
                ## calculate_elo_rank(player_a_rank=1600, player_b_rank=1600, winner=PLAYER_A, penalize_loser=True)
                new_winner_rank, new_loser_rank  = calculate_elo_rank(player_a_rank=attacker.rank ,player_b_rank=victim.rank )

                victim.rank = int(new_loser_rank)
                attacker.rank = int(new_winner_rank)
        
                if victim.btcBalance < self.minumumBTCHold:
                    kick_player = True
                    victim.kick = True
                    self.deactivatePlayer(victim_64, kick=True, message="Your balance is too low to continue playing.  Go to leetcoin.com to add more btc to your server hold.")
            
                self.matchkills = self.matchkills +1
        
                tell_all_players('%s earned: %s Satoshi for killing %s' %(attacker.name, self.kill_reward, victim.name))

            return kick_player, victim.btcBalance, attacker.btcBalance
            
        else:
            print("[1337] [recordKill] ERROR - Victim or attacker player object not found")
            tell_all_players('Non-Authorized player kill/death.  Authorize this server on www.leetcoin.com for tracking, and rewards!')
            return True, 0, 0

    def authorizeActivatePlayer(self, steam_64, userid):
        """ Kick off a thread to activate a player
        """
        if self.debug:
            print ("[1337] [authorizeActivatePlayer]")
        thread = ThreadedActivatePlayer(steam_64, userid, self, self.encryption, self.debug)
        thread.start()
        threads.append(thread)

    def threadActivatePlayer(self, userid, player_info):
        """ thread callback containing player_info """
        if self.debug:
            print ("[1337] [threadActivatePlayer]")
            print ("[1337] [threadActivatePlayer] player_info: %s"% player_info)
            print ("[1337] [threadActivatePlayer] userid: %s"% userid)
            
        if player_info['player_authorized']:
            if self.debug:
                print ("[1337] [threadActivatePlayer] Player authorized.")
                
            btc_hold = int(player_info['player_btchold'])
            if btc_hold >= self.minumumBTCHold:
                if self.debug:
                    print ("[1337] [threadActivatePlayer] Balance >= minumum")
                    
                index, player_obj = self.getPlayerObjByPlatformID(player_info['player_platformid'])
                
                self.players_connected = True
        
                if player_obj:
                    if self.debug:
                        print ("[1337] [authorizeActivatePlayer] Player Obj found in player obj list")
                    ## Update the existing player record with the latest from the API server
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
                        print ("[1337] [authorizeActivatePlayer] Player Obj NOT found in player obj list - adding")
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
                        self.authorizedPlayerObjectList.append(player_obj)
            
            else:
                if self.debug:
                    print ("[1337] [threadActivatePlayer] Player balance too low.")
                doKick(userid, "Your balance is too low to play on this server.  Go to leetcoin.com to add more to your balance.", True)
                
                thread = ThreadedDeactivatePlayer(player_info['player_platformid'], self, self.encryption, self.debug, False, "low balance")
                thread.start()
        else:
            if self.debug:
                print ("[1337] [threadActivatePlayer] Player NOT authorized.")
                
            if self.allow_non_authorized_players:
                if self.debug:
                    print ("[1337] [threadActivatePlayer] Non-Authorized players are PERMITTED")
            else:
                doKick(userid, "This server is not authorized for you.  Go to leetcoin.com to authorize it.", True)
                
                
                thread = ThreadedDeactivatePlayer(player_info['player_platformid'], self, self.encryption, self.debug, False, "not authorized")
                thread.start()

    def deactivatePlayer(self, steam_64, kick=False, message="You have been kicked from the server.  Go to leetcoin.com to verify your balance and authorization status."):
        """ Fire off a thread to deactivate the player """
        if self.debug:
            print ("[1337] deactivatePlayer")
        #index, player_obj = self.getPlayerObjByPlatformID(steam_64)
        #if player_obj:
        thread = ThreadedDeactivatePlayer(steam_64,  self, self.encryption, self.debug, kick, message)
        thread.start()
        #threads.append(thread)
        
    def threadDectivatePlayer(self, player_info, kick, message):
        """ thread callback containing player_info """
        if self.debug:
            print ("[1337] [threadDectivatePlayer]")
            print ("[1337] [threadDectivatePlayer] player_info: %s"% player_info)
        
        index, player_obj = self.getPlayerObjByKey(player_info['player_key'])
        if player_obj:
            player_obj.disconnected = True
        if kick:
            if self.debug:
                print ("[1337] [threadDectivatePlayer] KICKING")
            doKick(player_obj.userid, message, True)
            
    def get_active_player_count(self):
        """ get the count of active conencted players """
        count = 0
        for player in self.authorizedPlayerObjectList:
            if not player.disconnected:
                count = count +1
        return count

    def threadKickPlayersByKey(self, player_keys, message):
        """ thread callback to kick players """
        if self.debug:
            print ("[1337] [threadKickPlayersByKey]")
            print ("[1337] [threadKickPlayersByKey] player_keys: %s"% player_keys)
        for player_key in player_keys:
            player_index, player_obj = self.getPlayerObjByKey(player_key)
            
            if self.debug:
                print ("[1337] [threadKickPlayersByKey] kicking player_key: %s" %player_key)
                print ("[1337] [threadKickPlayersByKey] kicking userid: %s"% player_obj.userid)
            
            doKick(player_obj.userid, message, True)
            
    def removePlayer(self, steam_64):
        """ remove a player from the authorizedPlayerOBJList """
        if self.debug:
            print ("[1337] removePlayer")
        index, player_obj = self.getPlayerObjByPlatformID(steam_64)
        if player_obj:
            self.authorizedPlayerObjectList.pop(index)
        
    def getServerInfo(self):
        """ Get server info from the API server """
        if self.debug:
            print ("[1337] getServerInfo")

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
        for index, player_obj in enumerate(self.authorizedPlayerObjectList):
            if player_obj.platformID == steam_64:
                player_found = True
                player_index = index
                player_object = player_obj
                
        if player_found:
            if self.debug:
                print ("[1337] [getPlayerObjByPlatformID] Player Found!")
                print ("[1337] [getPlayerObjByPlatformID] player_index: %s" %player_index)
                print ("[1337] [getPlayerObjByPlatformID] player_object: %s" %player_object)
            return player_index, player_object
        else:
            if self.debug:
                print ("[1337] [getPlayerObjByPlatformID] [ERROR] Player NOT Found!")
            return None, None
            
    def getPlayerObjByKey(self, key):
        """ get a player object from a key """
        if self.debug:
            print ("[1337] [getPlayerObjByKey]")
        
        player_found = False
        for index, player_obj in enumerate(self.authorizedPlayerObjectList):
            if player_obj.key == key:
                player_found = True
                player_index = index
                player_object = player_obj
                
        if player_found:
            if self.debug:
                print ("[1337] [getPlayerObjByKey] Player Found!")
                print ("[1337] [getPlayerObjByKey] player_index: %s" %player_index)
                print ("[1337] [getPlayerObjByKey] player_object: %s" %player_object)
            return player_index, player_object
        else:
            if self.debug:
                print ("[1337] [getPlayerObjByKey] Player NOT Found!")
            return None, None
            
    def getPlayerObjByUserid(self, userid):
        """ get a player object from a userid """
        if self.debug:
            print ("[1337] [getPlayerObjByUserid]")
        
        player_found = False
        for index, player_obj in enumerate(self.authorizedPlayerObjectList):
            if player_obj.userid == userid:
                player_found = True
                player_index = index
                player_object = player_obj
                
        if player_found:
            if self.debug:
                print ("[1337] [getPlayerObjByUserid] Player Found!")
                print ("[1337] [getPlayerObjByUserid] player_index: %s" %player_index)
                print ("[1337] [getPlayerObjByUserid] player_object: %s" %player_object)
            return player_index, player_object
        else:
            if self.debug:
                print ("[1337] [getPlayerObjByUserid] Player NOT Found!")
            return None, None
            
    def requestAward(self, amount, title, player):
        """ fire off a thread to check if we can issue an award. """
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

        ## we need to convert userid into leetcoin key
        #player_key_list = []
        #player_name_list = []

        player_index, player_obj = self.getPlayerObjByUserid(player)
        if not player_obj:
            print("CANNOT ISSUE AN AWARD - COULD NOT GET PLAYER")
            return False
            
        award = Award(player_obj.key, player_obj.userid, player_obj.name, amount, title)
            
        thread = threading.Thread(target=ThreadedRequestAward, args=(award, "md5", self))
        thread.start()
        threads.append(thread)
        
    def threadRequestAward(self, award_info, award ):
        """ handle the result from the thread request. """
        if self.debug:
            print ("[1337] [threadRequestAward]")
            print ("[1337] [threadRequestAward] award_info: %s"% award_info)
            print ("[1337] [threadRequestAward] award: %s"% award)
            
        if award_info['authorization']:
            if award_info['award_authorized'] == True:
                
                #award_details_zip = zip(award_title_list, player_list, player_name_list, amount_list)
                
                if self.debug:
                    print ("[1337] [threadRequestAward] AUTHORIZED!")
                    #print ("[1337] [threadRequestAward] award_details_zip: %s" %award_details_zip)
                
                if self.debug:
                    print ("[1337] [threadRequestAward] award[playerKey]: %s" %award.playerKey)
                    print ("[1337] [threadRequestAward] award[playerUserId]: %s" %award.playerUserId)
                    print ("[1337] [threadRequestAward] award[amount]: %s" %award.amount)
                    print ("[1337] [threadRequestAward] award[title]: %s" %award.title)
                    
                player_index, player_obj = self.getPlayerObjByUserid(award.playerUserId)
                if player_obj:
                    if self.debug:
                        print ("[1337] [threadRequestAward] old balance: %s" %player_obj.btcBalance)
                        
                    player_obj.btcBalance = player_obj.btcBalance + int(award.amount)
                    
                    if self.debug:
                        print ("[1337] [threadRequestAward] new balance: %s" %player_obj.btcBalance)
                
                    tell_all_players('%s earned: %s Satoshi for: %s' %(player_obj.name, award.amount, award.title))

    def _get_https_response(self, params, uri):
        """ Perform the https post connection and return the results """
        if self.debug:
            print ("[1337] get_https_response %s" %uri)
        params = urllib.urlencode(params)
        H = md5.new(self.shared_secret)
        H.update(params)
        sign = H.hexdigest()
        headers = { "Content-type": "application/x-www-form-urlencoded", "Key":self.api_key, "Sign":sign }
        conn = httplib.HTTPConnection(self.url)
        conn.request("POST", uri, params, headers)
        response = conn.getresponse()
        
        return response.read()

class ThreadedSubmitMatchResults(threading.Thread):
    def __init__(self, threadID, name, apiClient, players_connected, matchkills, authorizedPlayerObjectList, active_players_changed, encryption, debug):
        threading.Thread.__init__(self)
        if debug:
            print("[1337] [ThreadedSubmitMatchResults] init")
        self.threadID = threadID
        self.name = name
        self.apiClient = apiClient
        self.players_connected = players_connected
        self.matchkills = matchkills
        self.authorizedPlayerObjectList = authorizedPlayerObjectList
        self.active_players_changed = active_players_changed
        self.encryption = encryption
        self.debug = debug
        
    def run(self):
        threadLock.acquire()

        if self.debug:
            print("[1337] [ThreadedSubmitMatchResults] run")
        if self.players_connected:
            if self.debug:
                print("[1337] [ThreadedSubmitMatchResults] Players Connected")
            if self.matchkills > 0:
                if self.debug:
                    print("[1337] [ThreadedSubmitMatchResults] matchkills > 0")
                    
                player_dict_list = []
                for index, player_obj in enumerate(self.authorizedPlayerObjectList):
                    player_dict_list.append(player_obj.to_dict())
                    
                    # reset
                    player_obj.kills = 0
                    player_obj.deaths = 0
                    # deactivate if disconnected
                    if player_obj.disconnected or player_obj.kick:
                        ## remove the player from the apiClient object list
                        self.apiClient.removePlayer(player_obj.platformID)
                    
                        self.active_players_changed = True
                        if self.debug:
                            print("[1337] [THREAD] authorizedPlayerObjectList NEW size: %s" %len(self.authorizedPlayerObjectList))
                            
                        if len(self.authorizedPlayerObjectList) < 1:
                            if self.debug:
                                print("[1337] [THREAD] setting players_connected to False")
                            self.apiClient.players_connected = False
                            
                self.apiClient.matchkills = 0
            
                if self.debug:
                    print "player_dict_list: %s" %player_dict_list
            
                uri = "/api/put_match_results"
                
                player_json_list = json.dumps(player_dict_list)
                
                params = OrderedDict([
                                  ("encryption", self.encryption),
                                  ("map_title", "Unknown"),
                                  ("nonce", time.time()),
                                  ("player_dict_list", player_json_list),
                                  ])
                

                response_json = get_https_response(params, uri, self.debug)
                response_obj = json.loads(response_json)

                #if response_obj['serverInfoRefreshNeeded'] == True:
                #    if self.debug:
                #        print("[1337] [THREAD] GOT serverInfoRefreshNeeded command from API")
                        
                if len(response_obj['playersToKick']) > 0:
                    if self.debug:
                        print("[1337] [THREAD] GOT playersToKick results from API")
                        
                    player_keys = response_obj['playersToKick']
                        
                    self.apiClient.threadKickPlayersByKey(player_keys, "You were kicked by the leetcoin API" )
                            
                threadLock.release()
                
                if self.debug:
                    print("[1337] [THREAD] response_json: %s" %response_json)
                
                return response_json
            else:
                if self.debug:
                    print("[1337] [THREAD] No Kills - Skipping")
                threadLock.release()
                return False
        else:
            if self.debug:
                print("[1337] [THREAD] No Players - Skipping")
            threadLock.release()
            return False



def ThreadedRequestAward(award, encryption, apiClient):
    uri = "/api/issue_award"
    
    award_json = json.dumps(award.to_dict())
    
    params = OrderedDict([
            ("award", award_json),
            ("encryption", encryption),
            ("nonce", time.time()),
              ])
    response = get_https_response(params, uri, False)
    award_info = json.loads(response)
    apiClient.threadRequestAward(award_info, award )

class ThreadedActivatePlayer(threading.Thread):
    """ activate a player
        This thread runs without a lock, and does not get added to the thread list.

    """
    def __init__(self, platformid, userid, apiClient, encryption, debug):
        threading.Thread.__init__(self)
        if debug:
            print("[1337] [ThreadedActivatePlayer] init")
        self.apiClient = apiClient
        self.userid = userid
        self.platformid = platformid
        self.encryption = encryption
        self.debug = debug
        
    def run(self):
        if self.debug:
            print("[1337] [ThreadedActivatePlayer] run")
        uri = "/api/activate_player"
        params = OrderedDict([
            ("encryption", self.encryption),
            ("nonce", time.time() ),
            ("platformid", self.platformid),
        ])
        response = get_https_response(params, uri, self.debug)
        player_info = json.loads(response)
        self.apiClient.threadActivatePlayer(self.userid, player_info)

class ThreadedDeactivatePlayer(threading.Thread):
    """ activate a player
        This thread runs without a lock, and does not get added to the thread list.
    """
    def __init__(self, platformid, apiClient, encryption, debug, kick, message):
        threading.Thread.__init__(self)
        if debug:
            print("[1337] [ThreadedDeactivatePlayer] init")

        self.apiClient = apiClient
        self.platformid = platformid
        #self.player_obj = player_obj
        self.encryption = encryption
        self.debug = debug
        self.kick = kick
        self.message = message
        
    def run(self):
        if self.debug:
            print("[1337] [ThreadedDeactivatePlayer] run")
        uri = "/api/deactivate_player"
        params = OrderedDict([
        
            ("encryption", self.encryption),
            ("nonce", time.time()),
            ("platformid",self.platformid),
            #("rank", self.player_obj.rank),
            #("satoshi_balance", self.player_obj.btcBalance),
            
        ])
        response = get_https_response(params, uri, self.debug)
        player_info = json.loads(response)
        self.apiClient.threadDectivatePlayer(player_info, self.kick, self.message)
            
def get_https_response(params, uri, debug):
    """ Perform the https post connection and return the results """
    if debug:
        print ("[1337] get_https_response %s" %uri)
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
    es.server.queuecmd("kickid %s Reason: %s" % (userid, message))
        
def calculate_elo_rank(player_a_rank=1600, player_b_rank=1600, penalize_loser=True):
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
    
    
def tell_all_players(message):
    myPlayerList = playerlib.getPlayerList()
    for ply in myPlayerList:
        es.tell(ply.userid, message)
        
