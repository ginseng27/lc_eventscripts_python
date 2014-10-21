# Import Python Modules
import es, re, md5, playerlib, repeat
import gamethread
import threading
import playerlib
import urllib, httplib, time, hashlib, hmac
import threading

## This is now loaded via the site-packages folder instead of via the egg method
try: import simplejson as json
except ImportError: print ("Json Import Error")

# Import Config
from config import *

# Import leetcoin API client
from leetcoin_api_client import LeetCoinAPIClient

# instanciate API client
leetcoin_client = LeetCoinAPIClient(url, api_key, shared_secret, "md5")

# Variables
steamIDBase = 76561197960265728
encrypt = 'md5'

def load():
    myRepeat = repeat.create('serverUpdate', serverUpdate, ())
    myRepeat.start(60, 1200000000)
    
    # In game Commands
    if not es.exists('saycommand', '/help'):
        es.regsaycmd('/help', 'leetcoin/help')
    if not es.exists('saycommand', '/balance'):
        es.regsaycmd('/balance', 'leetcoin/getBalance')
    if not es.exists('saycommand', '/rank'):
        es.regsaycmd('/rank', 'leetcoin/getRank')

def unload():
    repeat.delete('serverUpdate')

def serverUpdate():
    leetcoin_client.repeatingServerUpdate()

# Player Death Event
def player_death(event_var):
    victim = str(event_var['es_steamid'])
    print("victim: %s" % victim)
    
    attacker = str(event_var['attacker'])
    print("attacker: %s" % attacker)
    
    if attacker == 'BOT' or victim == 'BOT':
        print "Error 1: Bot Encountered"
    else:
        victim_64 = str(convertSteamIDToCommunityID(victim))
        #attacker_64 = str(convertSteamIDToCommunityID(attacker))
        kick_player, v_balance, a_balance = leetcoin_client.recordKill(victim_64, attacker)
        es_player = str(event_var['userid'])
        getBalance(es_player)

def player_connect(event_var):
    steam_id = event_var['networkid']
    userid = event_var['userid']
    print("steam_id: '%s' userid: '%s'" % (steam_id, userid))
    steam_64 = str(convertSteamIDToCommunityID(steam_id))
    print("player connected - steamid: %s, userid: %s" % (steam_64, userid))
    authorized_active_player = leetcoin_client.authorizeActivatePlayer(steam_64, userid)

def player_disconnect(event_var):
    steam_id = event_var['networkid']
    steam_64 = str(convertSteamIDToCommunityID(steam_id))
    print("player disconnected - steamid: %s" % steam_64)
    deactivated_result = leetcoin_client.deactivatePlayer(steam_64)

def help(es_player=None):
    # Tell Player the help options
    if not es_player:
        es_player = es.getcmduserid()
    steamid = es.getplayersteamid(es_player)
    steam_64 = str(convertSteamIDToCommunityID(steamid))
    es.tell(es_player, "Available commands are:  /balance /rank")

def getBalance(es_player=None):
    # Tell Player their Current Balance
    if not es_player:
        es_player = es.getcmduserid()
    steamid = es.getplayersteamid(es_player)
    steam_64 = str(convertSteamIDToCommunityID(steamid))
    es.tell(es_player, leetcoin_client.getPlayerBalance(steam_64))

def getRank(es_player=None):
    # Tell Player their Current Rank
    if not es_player:
        es_player = es.getcmduserid()
    steamid = es.getplayersteamid(es_player)
    steam_64 = str(convertSteamIDToCommunityID(steamid))
    es.tell(es_player, leetcoin_client.getPlayerRank(steam_64))

# Covnert Steam ID to Steam64
def convertSteamIDToCommunityID(steamID):
    print "convertSteamIDToCommunityID, steamID: %s" % steamID
    steamIDParts = re.split(":", steamID)
    communityID = int(steamIDParts[2].strip("]")) * 2
    if steamIDParts[1] == "1":
        communityID += 1
    communityID += steamIDBase
    return communityID

def round_start(event_var):
    print("[][][][][][][][] ROUND START [][][][][][][][[][]]")
    
def round_end(event_var):
    print("[][][][][][][][] ROUND END [][][][][][][][[][]]")
    #leetcoin_client.repeatingServerUpdate()
    
    winner = event_var['winner']
    reason = event_var['reason']
    message = event_var['message']
    
    print("winner: %s" %winner)
    print("reason: %s" %reason)
    print("message: %s" %message)
    
    # [][][][][][][][] ROUND END [][][][][][][][[][]]
    # winner: 1
    # reason: 9
    # message: #Round_Draw
    
    # winner: 3
    # reason: 10
    # message: #All_Hostages_Rescued
    
    # winner: 3
    # reason: 7
    # message: #CTs_Win
    
    # winner: 2
    # reason: 8
    # message: #Terrorists_Win
    
    # winner: 1
    # reason: 15
    # message: #Game_Commencing
    
def bomb_defused(event_var):
    print("[][][][][][][][] BOMB DEFUSED [][][][][][][][[][]]")
    if award_defuse_bomb:
        
        #steam_id = event_var['networkid']
        #steam_64 = str(convertSteamIDToCommunityID(steam_id))
        #print("bomb_defused - steamid: %s" % steam_64)
        
        userid = event_var['userid']
        print("bomb_planted - userid: %s" % userid)
        
        username = event_var['username']
        print("bomb_planted - username: %s" % username)
        
        #team_number = event_var['team_number']
        #print("bomb_planted - team_number: %s" % team_number)
        
        #amount_list = []
        #amount_list.append(award_defuse_bomb_amount)
        #award_title_list = []
        #award_title_list.append(award_defuse_bomb_title)
        #player_list = []
        #player_list.append(userid)
    
        leetcoin_client.requestAward(award_defuse_bomb_amount, award_defuse_bomb_title, userid)
    
def bomb_planted(event_var):
    print("[][][][][][][][] BOMB PLANTED [][][][][][][][[][]]")
    
    if award_plant_bomb:
        
        ## Thisd is blank.
        #networkid = event_var['networkid']
        #print("bomb_planted - networkid: %s" % networkid)
        
        # this does not exist even though it is in the docs
        #steam_id = event_var['es_steamid']
        #print("bomb_planted - es_steamid: %s" % es_steamid)
        
        #steamid = event_var['steamid']
        #print("bomb_planted - steamid: %s" % steamid)
        
        #steam_64 = str(convertSteamIDToCommunityID(steam_id))
        #print("bomb_planted - steamid: %s" % steam_64)
        
        userid = event_var['userid']
        print("bomb_planted - userid: %s" % userid)
        
        username = event_var['username']
        print("bomb_planted - username: %s" % username)
        
        #team_number = event_var['team_number']
        #print("bomb_planted - team_number: %s" % team_number)
        
        #amount_list = []
        #amount_list.append(award_plant_bomb_amount)
        #award_title_list = []
        #award_title_list.append(award_plant_bomb_title)
        #player_list = []
        #player_list.append(userid)
    
        leetcoin_client.requestAward(award_plant_bomb_amount, award_plant_bomb_title, userid)
        
def teamplay_point_captured(event_var):
    print("[][][][][][][][] POINT CAPTURED [][][][][][][][[][]]")
    cp = event_var['cp']
    cpname = event_var['cpname']
    team = event_var['team']
    cappers = event_var['cappers']
    
def server_spawn(event_var):
    print("[][][][][][][][] SERVER SPAWN [][][][][][][][[][]]")
    
    




    
