# -*- coding: utf-8 -*-
# pylint: disable=C0103
# pylint: disable=W0702
# pylint: disable=R0912
# pylint: disable=R0915
# pylint: disable=R0914

"""Arsenic development

This is WIP code under active development.

"""
import ConfigParser
import cProfile
import imp
import os
import pstats
import sqlite3
import StringIO
import sys
import time

from twisted.internet import protocol, reactor, ssl
from twisted.python import log
from twisted.words.protocols import irc

pr = cProfile.Profile()

VER = '0.1.59'
file_log = 'kgb-' + time.strftime("%Y_%m_%d-%H%M%S") + '.log'
print "THE_KGB %s, log: %s" % (VER, file_log)
log.startLogging(open(file_log, 'w'))

config_dir = ''

cfile = open(os.path.join(config_dir, 'kgb.conf'), 'r')
config = ConfigParser.ConfigParser()
config.readfp(cfile)
cfile.close()

oplist = config.get('main', 'op').translate(None, " ").split(',')

modlook = {}
modules = config.get('main', 'mod').translate(None, " ").split(',')

mod_declare_privmsg = {}
mod_declare_userjoin = {}

channel_user = {}

irc_relay = ""

isconnected = False

try:
    irc_relay = config.get('main', 'log')
except:
    log.msg("no relay log channel")

db_name = ""

try:
    db_name = config.get('main', 'db')
except:
    db_name = ""

if os.path.isfile(db_name) is False:
    log.err("No database found!")
    raise SystemExit(0)

class conf(Exception):

    """Automatically generated"""


class LogBot(irc.IRCClient):

    """Twisted callbacks registered here"""

    def __init__(self):
        return

    nickname = config.get('main', 'name')

    def isauth(self, user):
        """Checks if hostmask is bot op"""

        user_host = user.split('!', 1)[1]

        try:  # needed for non message op commands
            c = conn.execute(
                'select * from op where username = ?', (user_host,))
        except:
            c = None

        if c is not None:

            if user_host in oplist:
                return True

            elif c.fetchone() is not None:
                return True

            else:
                return False

        else:
            if user_host in oplist:
                return True

            else:
                return False

    def connectionMade(self):
        irc.IRCClient.connectionMade(self)
        self.msg('NickServ', 'identify ' + self.factory.nspassword)

    def connectionLost(self, reason):
        irc.IRCClient.connectionLost(self, reason)

    # callbacks for events
    def signedOn(self):
        for i in channel_list:
            channel_user[i.lower()] = [self.nickname]
            self.join(i)

    def kickedFrom(self, channel, user, message):
        self.join(channel)
        del user

    def userJoined(self, cbuser, cbchannel):
        for command in mod_declare_userjoin:
            modlook[
                mod_declare_userjoin[command]].callback(
                self,
                "userjoin",
                False,
                user=cbuser,
                channel=cbchannel)


    def privmsg(self, user, channel, msg):
        user = user.split('^', 1)[0]
        if user == self.nickname:
            return

        auth = self.isauth(user)

# Start module execution

        command = msg.split(' ', 1)[0].lower()

        if channel == self.nickname:

            if command in mod_declare_privmsg:
                modlook[
                    mod_declare_privmsg[command]].callback(
                    self,
                    "privmsg",
                    auth,
                    command,
                    msg=msg,
                    user=user,
                    channel=channel)

            # private commands
            if irc_relay != "":
                self.msg(irc_relay, user + " said " + msg)

            if auth:
                if msg.startswith('op'):

                    host = msg.split(' ', 1)[1]
                    extname = host.split('!', 1)[0]
                    c = conn.execute('insert into op(username) values (?)',
                                     (host.split('!', 1)[1],))
                    conn.commit()

                    self.msg(
                        user.split(
                            '!',
                            1)[0],
                        'Added user %s to the op list' %
                        (extname))
                    self.msg(extname, "You've been added to my op list")

                elif msg.startswith('deop'):

                    host = msg.split(' ', 1)[1]
                    extname = host.split('!', 1)[0]
                    c = conn.execute('delete from op where username = ?',
                                     (host.split('!', 1)[1],))
                    conn.commit()

                    self.msg(
                        user.split(
                            '!',
                            1)[0],
                        'Removed user %s from the op list' %
                        (extname))

                elif msg.startswith('add'):

                    cmd = msg.split(' ', 2)[1].lower()
                    data = msg.split(' ', 2)[2]

                    conn.execute(
                        ('insert or replace into command(name, response) '
                         'values (?, ?)'), (cmd, data))
                    conn.commit()

                    self.msg(
                        user.split(
                            '!', 1)[0], 'Added the command %s with value %s' %
                        (cmd, data))

                elif msg.startswith('del'):

                    cmd = msg.split(' ')[1].lower()

                    conn.execute('delete from command where name = ?',
                                 (cmd,))
                    conn.commit()

                    self.msg(
                        user.split(
                            '!',
                            1)[0],
                        'Removed command %s' %
                        (cmd))

                elif msg.startswith('prof_on'):
                    pr.enable()
                    u = user.split('!', 1)[0]
                    self.msg(u, 'profiling on')

                elif msg.startswith('prof_off'):
                    pr.disable()
                    u = user.split('!', 1)[0]
                    self.msg(u, 'profiling on')

                elif msg.startswith('prof_stat'):
                    u = user.split('!', 1)[0]
                    s = StringIO.StringIO()
                    sortby = 'cumulative'
                    ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
                    ps.print_stats()
                    self.msg(u, s.getvalue())

                elif msg.startswith('mod_reload'):
                    mod = msg.split(' ')[1]

                    mod_src = open(config_dir + '/app/' + mod + '.py')
                    mod_bytecode = compile(mod_src.read(), '<string>', 'exec')
                    mod_src.close()

                    exec mod_bytecode in modlook[mod].__dict__

                    declare_table = modlook[mod].declare()

                    for i in declare_table:
                        cmd_check = declare_table[i]

                        if cmd_check == 'privmsg':
                            mod_declare_privmsg[i] = mod

                        elif cmd_check == 'userjoin':
                            mod_declare_userjoin[i] = mod

                elif msg.startswith('mod_load'):
                    mod = msg.split(' ')[1]

                    mod_src = open(config_dir + '/app/' + mod + '.py')
                    mod_bytecode = compile(mod_src.read(), '<string>', 'exec')

                    modlook[mod] = imp.new_module(mod)
                    sys.modules[mod] = modlook[mod]

                    exec mod_bytecode in modlook[mod].__dict__

                    declare_table = modlook[mod].declare()

                    for i in declare_table:
                        cmd_check = declare_table[i]

                        if cmd_check == 'privmsg':
                            mod_declare_privmsg[i] = mod

                        elif cmd_check == 'userjoin':
                            mod_declare_userjoin[i] = mod

                elif msg.startswith('inject'):
                    self.lineReceived(msg.split(' ',1)[1])

                elif msg.startswith('raw'):
                    self.sendLine(msg.split(' ',1)[1])

                elif msg.startswith('help'):
                    u = user.split('!', 1)[0]
                    self.msg(u, 'Howdy, %s, you silly operator.' % (u))
                    self.msg(u, 'You have access to the following commands:')
                    self.msg(u, 'add {command} {value}, del {command}')
                    self.msg(u, 'join {channel}, leave {channel}')
                    self.msg(u, 'nick {nickname}, topic {channel} {topic}')
                    self.msg(u, 'kick {channel} {name} {optional reason}')
                    self.msg(u, 'ban/unban {channel} {hostmask}')
                    self.msg(u, 'msg {channel} {message}')

            else:
                u = user.split('!', 1)[0]
                self.msg(u, 'I only accept commands from bot operators')

        elif msg.startswith('^'):

            if command[1:] in mod_declare_privmsg:
                modlook[
                    mod_declare_privmsg[
                        command[
                            1:]]].callback(
                    self,
                    "privmsg",
                    auth,
                    command[
                        1:],
                    msg,
                    user,
                    channel)

            elif msg.startswith('^help'):
                u = user.split('!', 1)[0]

                commands = []
                c = conn.execute('select name from command')
                for cmd in modules:
                    commands.append("^" + cmd)

                for command in c:
                    commands.append("^" + str(command[0]))

                self.msg(u, 'Howdy, %s' % (u))
                self.msg(u, 'You have access to the following commands:')

                self.msg(u, ', '.join(commands))

            else:
                command = command[1:]
                c = conn.execute(
                    'select response from command where name == ?', (command,))

                r = c.fetchone()
                if r is not None:
                    try:
                        u = msg.split(' ')[1]
                        self.msg(channel, "%s: %s" % (u, str(r[0])))

                    except:
                        self.msg(channel, str(r[0]))


    def lineReceived(self, line): #ACTUAL WORK
                                  #Twisted API emulation

        global isconnected

        data = ''
        channel = ''
        server = ''
        user = ''
        command = ''
        victim = ''

        raw_line = line
        line = line.split(' ') #:coup_de_shitlord!~coup_de_s@fph.commiehunter.coup PRIVMSG #FatPeopleHate :the raw output is a bit odd though

        try:
            if line[0].startswith(':'): #0 is user, so 1 is command
                user = line[0].split(':',1)[1]
                command = line[1]

                if command.isdigit() == False: #on connect we're spammed with commands that aren't valid

                    if line[2].startswith('#'): #PRIVMSG or NOTICE in channel
                        channel = line[2]

                        if command == 'KICK': #It's syntax is normalized for :
                            victim = line[3]
                            data = raw_line.split(' ',4)[4].split(':',1)[1]

                        elif command == 'MODE':
                            victim = line[4]
                            data = line[3]

                        elif command == 'PART':
                            if len(line) == 4: #Implies part message
                                data = raw_line.split(' ',3)[3].split(':',1)[1]
                            else:
                                data = ''

                        else:
                            if line[3] == ':ACTION': #/me, act like normal message
                                data = raw_line.split(' ',4)[4].split(':',1)[1]
                            else:
                                data = raw_line.split(' ',3)[3].split(':',1)[1]

                    elif line[2].startswith(':#'): #JOIN/KICK/ETC
                        channel = line[2].split(':',1)[1]

                    else: #PRIVMSG or NOTICE via query
                        channel = self.nickname

                        if line[2] == ':ACTION': #/me, act like normal message
                            data = raw_line.split(' ',3)[3].split(':',1)[1]
                        else:
                            data = raw_line.split(' ',2)[2].split(':',1)[1]

            else:
                command = line[0] #command involving server
                server = line[1].split(':',1)[1]

            if command.isdigit() == False:

                if command == 'NOTICE' and 'connected' in data.lower() and isconnected == False:
                                                    #DIRTY FUCKING HACK
                                                    #100% UNSAFE. DO NOT USE THIS IN PRODUCTION
                                                    #Proposed fixes: No idea, need to google things

                    self.connectionMade()
                    self.signedOn()
                    isconnected = True #dirter hack, makes sure this only runs once

                log_data = "Command: %s, user: %s, channel: %s, data: %s, victim: %s, server: %s" % (command, user, channel, data, victim, server)
                log.msg(log_data)

                if command == 'PING':
                    self.sendLine('PONG ' + server)

                elif command == 'PRIVMSG': #privmsg(user, channel, msg)
                    self.privmsg(user, channel, data)

                elif command == 'JOIN':
                    user = user.split('!',1)[0]
                    self.userJoined(user, channel)
                    channel_user[channel.lower()] = [user.strip('~%@+&')]

                elif command == 'PART':
                    user = user.split('!',1)[0]

                    if channel.lower() in channel_user:
                        if user in channel_user[channel.lower()]:
                            channel_user[channel.lower()].remove(user)
                        else:
                            log.err("Warning: Tried to remove unknown user. (%s)" % (user))

                    else:
                        log.err("Warning: Tried to remove user from unknown channel. (%s, %s)" % (channel.lower(), user))

                elif command == 'QUIT':
                    user = user.split('!',1)[0]

                    for i in channel_user:
                        if user in channel_user[i]:
                            channel_user[i].remove(user)

                elif command == 'NICK':
                    user = user.split('!',1)[0]

                    if channel.lower() in channel_user:
                        if user in channel_user[channel.lower()]:
                            channel_user[channel.lower()].remove(user)
                        else:
                            log.err("Warning: Tried to remove unknown user. (%s)" % (user))

                    else:
                        log.err("Warning: Tried to remove user from unknown channel. (%s, %s)" % (channel.lower(), user))

                    channel_user[channel.lower()] = [data]

                elif command == 'KICK':
                    if victim.split('!') == self.nickname: #checks if we got kicked
                        self.kickedFrom(channel, victim, data)


            elif line[1] == '353': #NAMES output
                if line[3].startswith('#'):
                    channel = line[3].lower()
                    raw_user = raw_line.split(' ', 4)[4].split(':',1)[1]
                else:
                    channel = line[4].lower()
                    raw_user = raw_line.split(' ', 5)[5].split(':',1)[1]

                if channel not in channel_user:
                    channel_user[channel] = [self.nickname]

                for i in raw_user.split(' '):

                    if i not in channel_user[channel]:
                        channel_user[channel].append(i.strip('~%@+&'))

        except:
            log.err("Error: %s" % (raw_line))

class LogBotFactory(protocol.ClientFactory):

    """Main irc connector"""

    def __init__(self, conn, channel, username, nspassword):
        self.conn = conn
        self.channel = channel

        self.username = username
        self.nspassword = nspassword

    def buildProtocol(self, addr):
        p = LogBot()
        p.factory = self
        return p

    def clientConnectionLost(self, connector, reason):
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        log.err("connection failed: %s" % (reason))
        reactor.stop()


if __name__ == '__main__':
    conn = sqlite3.connect(db_name)

    try:
        if sys.argv[1].startswith('--config='):
            config_dir = sys.argv[1].split('=', 1)[1]
            if config_dir == '':
                raise conf('No path specified')
            else:
                if not os.path.isdir(config_dir):
                    raise conf('config path not found')
                    raise
    except:
        raise conf(
            'arsenic takes a single argument, --config=/path/to/config/dir')

    for mod in modules:
        mod_src = open(config_dir + '/app/' + mod + '.py')
        mod_bytecode = compile(mod_src.read(), '<string>', 'exec')
        mod_src.close()

        modlook[mod] = imp.new_module(mod)
        sys.modules[mod] = modlook[mod]
        exec mod_bytecode in modlook[mod].__dict__

        declare_table = modlook[mod].declare()

        for i in declare_table:
            cmd_check = declare_table[i]

            if cmd_check == 'privmsg':
                mod_declare_privmsg[i] = mod

            elif cmd_check == 'userjoin':
                mod_declare_userjoin[i] = mod

    try:
        channel_list = config.get('main', 'channel').translate(None, " ").split(',')

        f = LogBotFactory(conn, channel_list[0], config.get('main', 'name'),
                          config.get('main', 'password'))
    except IndexError:
        raise SystemExit(0)

    reactor.connectSSL(
        config.get(
            'network', 'hostname'), int(
            config.get(
                'network', 'port')), f, ssl.ClientContextFactory())

    reactor.run()
