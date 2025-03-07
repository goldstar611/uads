PKT_FLAG_NONE = 0x0
PKT_FLAG_PART = 0x1
PKT_FLAG_GARANT = 0x2
PKT_FLAG_ASYNC = 0x4
PKT_FLAG_SYSTEM = 0x80
PKT_FLAG_MASK_SYSTEM = PKT_FLAG_SYSTEM
PKT_FLAG_MASK_NORMAL = PKT_FLAG_PART | PKT_FLAG_GARANT | PKT_FLAG_ASYNC

SYS_MSG_HANDSHAKE = 0x1
SYS_MSG_CONNECTED = 0x2
SYS_MSG_DISCONNECT = 0x3
SYS_MSG_PING = 0x5
SYS_MSG_DELIVERED = 0x7
SYS_MSG_RETRY = 0x8
SYS_MSG_LIST_GAMES = 0x30
SYS_MSG_SES_JOIN = 0x40  # Server->User if joined (or create). User->Server for request for join
SYS_MSG_SES_LEAVE = 0x41  # User->Server request. Server->User kick/disconnect
SYS_MSG_SES_LEAD = 0x42  # Server->User
SYS_MSG_SES_CREATE = 0x43  # User->Server
SYS_MSG_SES_SHOW = 0x44  # User->Server
SYS_MSG_SES_KICK = 0x45  # User->Server
SYS_MSG_SES_CLOSE = 0x46  # User->Server Server->User
SYS_MSG_SES_ERR = 0x4F
SYS_MSG_CONNERR = 0x81

USR_MSG_DATA = 0x10
USR_MSG_LIST_GAMES = 0x30  # Server->User
USR_MSG_SES_USERJOIN = 0x40  # Broadcasting Server->[users]
USR_MSG_SES_USERLEAVE = 0x41  # Broadcasting Server->[users]
USR_MSG_SES_USERLIST = 0x42  # Server->User (list users in session)

UAMSG_BASE = 1000
UAMSG_LOAD = UAMSG_BASE + 0  # = 0x03e8
UAMSG_NEWVHCL = UAMSG_BASE + 1  # = 0x03e9
UAMSG_DESTROYVHCL = UAMSG_BASE + 2  # = 0x03ea
UAMSG_NEWLEADER = UAMSG_BASE + 3  # = 0x03eb
UAMSG_NEWWEAPON = UAMSG_BASE + 4  # = 0x03ec
UAMSG_SETSTATE = UAMSG_BASE + 5  # = 0x03ed
UAMSG_VHCLDATA_I = UAMSG_BASE + 6  # = 0x03ee
UAMSG_VHCLDATA_E = UAMSG_BASE + 7  # = 0x03ef
# = 0x03f0
UAMSG_DEAD = UAMSG_BASE + 9  # = 0x03f1
UAMSG_VHCLENERGY = UAMSG_BASE + 10  # = 0x03f2
UAMSG_SECTORENERGY = UAMSG_BASE + 11  # = 0x03f3
UAMSG_STARTBUILD = UAMSG_BASE + 12  # = 0x03f4
UAMSG_BUILDINGVHCL = UAMSG_BASE + 13  # = 0x03f5
UAMSG_VIEWER = UAMSG_BASE + 14  # = 0x03f6
UAMSG_SYNCGM = UAMSG_BASE + 15  # = 0x03f7
UAMSG_HOSTDIE = UAMSG_BASE + 16  # = 0x03f8
# +17 DEBUG = 0x03f9
UAMSG_MESSAGE = UAMSG_BASE + 18  # = 0x03fa
UAMSG_KICK = UAMSG_BASE + 19  # = 0x03fb
UAMSG_UPGRADE = UAMSG_BASE + 20  # = 0x03fc
UAMSG_FACTION = UAMSG_BASE + 21  # = 0x03fd
UAMSG_WELCOME = UAMSG_BASE + 22  # = 0x03fe
UAMSG_READY = UAMSG_BASE + 23  # = 0x03ff
UAMSG_REQUPDATE = UAMSG_BASE + 24  # = 0x0400
UAMSG_UPDATE = UAMSG_BASE + 25  # = 0x0401
UAMSG_IMPULSE = UAMSG_BASE + 26  # = 0x0402
UAMSG_LOGMSG = UAMSG_BASE + 27  # = 0x0403
UAMSG_REORDER = UAMSG_BASE + 28  # = 0x0404
UAMSG_LOBBYINIT = UAMSG_BASE + 29  # = 0x0405
UAMSG_STARTPLASMA = UAMSG_BASE + 30  # = 0x0406
UAMSG_ENDPLASMA = UAMSG_BASE + 31  # = 0x0407
# +32 SET VP = 0x0408
UAMSG_STARTBEAM = UAMSG_BASE + 33  # = 0x0409
UAMSG_ENDBEAM = UAMSG_BASE + 34  # = 0x040a
UAMSG_EXIT = UAMSG_BASE + 35  # = 0x040b
UAMSG_SETLEVEL = UAMSG_BASE + 36  # = 0x040c
UAMSG_CRC = UAMSG_BASE + 37  # = 0x040d
UAMSG_REQPING = UAMSG_BASE + 38  # = 0x040e
UAMSG_PONG = UAMSG_BASE + 39  # = 0x040f
UAMSG_STARTPROBLEM = UAMSG_BASE + 40  # = 0x0410
UAMSG_ENDPROBLEM = UAMSG_BASE + 41  # = 0x0411
UAMSG_CD = UAMSG_BASE + 42  # = 0x0412
UAMSG_SCORE = UAMSG_BASE + 43  # = 0x0413
