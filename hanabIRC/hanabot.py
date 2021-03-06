'''
    hanabot.py implements an IRC bot that plays Hanabi.

    It uses the hanabi.Game module Hanabi engine to 
    get strings to display on the channel and private
    messages to the player. 

    It primarly is responsible for connecting to the 
    channel, parsing incoming commands, and writing
    reponses from the game engine.
'''    
import logging
import time
import string
import random
import sys
import os
import traceback
from collections import defaultdict

from hanabi import Game
from irc.bot import SingleServerIRCBot
from irc.client import VERSION as irc_client_version

log = logging.getLogger(__name__)


class Hanabot(SingleServerIRCBot):
    def __init__(self, server, channel, nick='hanabot', nick_pass=None, port=6667, topic=None):
        log.debug('new bot started at %s:%d@#%s as %s', server, port,
                  channel, nick)
        SingleServerIRCBot.__init__(
            self,
            server_list=[(server, port)],
            nickname=nick,
            realname='Mumford J. Hanabot')

        self.nick_pass = nick_pass
        self.nick_name = nick  
        self.topic = topic

        # force channel to start with #
        self.initial_channel = channel if channel[0] == '#' else '#%s' % channel

        # valid bot commands
        self.command_dict = {
            'Game Management': ['new', 'delete', 'join', 'start', 'leave', 'part'],
            'Hand Management': ['move', 'swap', 'sort'],
            'Game Action': ['play', 'hint', 'discard'],
            'Information': ['help', 'rules', 'turn', 'turns', 'game',
                            'games', 'hands', 'table', 'discardpile']
        }
        
        self.commands = list()
        for cmds in self.command_dict.values():
            self.commands += cmds

        self.commands_admin = ['die']

        # these commands can execute without an active game.
        # otherwise the command handlers can assume an active game.
        self.no_game_commands = ['new', 'help', 'rules', 'game', 'games', 'part']

        # games is a dict indexed by channel name, value is the Game object.
        self.games = dict()

    # lib IRC callbacks
    #############################################################
    def get_version(self):
        '''raises exception in lib irc, so overload in the bot.'''
        return "Python irc.bot 8.0"

    def on_nicknameinuse(self, conn, event):
        conn.nick(conn.get_nickname() + "_")

    def on_welcome(self, conn, event):
        if self.nick_pass:
            msg = 'IDENTIFY %s %s' % (self.nick_name, self.nick_pass)
            self.connection.privmsg('NickServ', msg)

        conn.join(self.initial_channel)

    def on_kick(self, conn, event):
        time.sleep(1)
        conn.join(self.channel)
        conn.notice(self.channel, 'Why I outta....')

    def on_join(self, conn, event):
        log.debug('got on_join: %s %s', conn, event)
        if self.topic:
            self.connection.topic(event.target, self.topic)

    def on_privmsg(self, conn, event):
        log.debug('got privmsg. %s -> %s', event.source, event.arguments)
        self.on_pubmsg(event, event)

    def on_pubmsg(self, conn, event):
        try:
            log.debug('got pubmsg. %s -> %s', event.source, event.arguments)
            # messaged commands
            a = event.arguments[0].split(':', 1)
            if len(a) > 1 and string.lower(a[0]) == string.lower(
                    self.connection.get_nickname()):
                self.parse_commands(event, [a[1].strip()] + event.arguments[1:])

            # general channel commands
            if len(event.arguments[0]) and event.arguments[0][0] == '!':
                log.debug('got channel command: %s', event.arguments[0][1:])
                # rebuild the list w/out the ! at start of the first arg
                self.parse_commands(event,
                                    [event.arguments[0][1:]] + event.arguments[1:])
        except Exception, e:
            log.critical('Got exception when handling message: %s' % e)

    def parse_commands(self, event, cmds):
        try:
            log.debug('got command. %s --> %s : %s',
                      event.source.nick, event.target, event.arguments)
            nick = event.source.nick
            if not cmds:
                return ([], 'Giving a command would be more useful.')

            # I don't understand when args will ever be more than just a string of
            # space separated words - need more IRC lib experience or docs.
            cmds = [str(c) for c in cmds[0].split()]

            # op only commands - return after executing.
            if cmds[0] in self.commands_admin:
                log.debug('running admin cmd %s', cmds[0])
                for chname, chobj in self.channels.items():
                    if nick in chobj.opers():
                        if cmds[0] == 'die':
                            self.die('Seppuku Successful')

                        return

            # valid user command check
            if not cmds[0] in self.commands:
                self._to_nick(event, 'My dearest brother Willis, I do not '
                              'understand this "%s" of which you speak.' %
                              ' '.join(cmds))
                return
            # call the appropriate handle_* function.
            method = getattr(self, 'handle_%s' % cmds[0], None)
            if method:
                if not cmds[0] in self.no_game_commands:
                    if not event.target in self.games:
                        msg = 'There is no active game in %s! Start one with !new.' % event.target
                        self._to_chan(event, msg)
                        return
                
                # invoke it!
                method(cmds[1:], event)

        except Exception, e:
            exc_type, exc_value, exc_tb = sys.exc_info()
            filename, line_num, func_name, text = traceback.extract_tb(exc_tb)[-1]
            filename = os.path.basename(filename)
            errs = ['Exception in parse_command: %s' % e, 
                    'Error in file %s:%s in %s().' % (filename, line_num, func_name),
                    'Error text: %s' % text]
            self._to_chan(event, 'Does not compute. Unknown error happened. All bets are'
                          ' off about game(s) state. Guru contemplation haiku:')
            for err in errs:
                log.critical('%s', err)
                self._to_chan(event, err)

    # some sugar for sending msgs
    def _display(self, output, event):
        '''Output is the list of (public, private) msgs generated
        byt the Game engine. nick is the user to priv message.
        output == (string list, string list).'''
        for l in output[0]:
            self.connection.notice(event.target, l)

        for l in output[1]:
            self.connection.notice(event.source.nick, l)

    # some sugar for sending msgs
    def _to_chan(self, event, msgs):
        if isinstance(msgs, list):
            self._display((msgs, []), event)
        elif isinstance(msgs, (str, unicode)):
            self._display(([msgs], []), event)

    # some sugar for sending strings
    def _to_nick(self, event, msgs):
        if isinstance(msgs, list):
            self._display(([], msgs), event)
        elif isinstance(msgs, (str, unicode)):
            self._display(([], [msgs]), event)

    # Game Commands
    #############################################################
    def handle_help(self, args, event):
        log.debug('got help event. args: %s', args)
        if not args:
            usage = list()
            usage.append(
                'A game is created via !new, then 2 to 5 people !join the '
                'game, and someone calls !start to start the game. Once '
                'started, players take turns either !playing a card, '
                '!discarding a card, or giving another player a !hint. '
                'After a valid !play or !discard the state of the '
                'table is shown. The table state can also be seen '
                'with the !table command. The turn order is shown with !turns.')
            usage.append(
                'Players can use !hands to view all hands at the table, '
                'including their own. Your own hand is shown with the "backs" '
                'facing you. When any card is added to your hand, it is assigned '
                ' a letter A-E, allowing you to track individial cards as they move around.'
                ' When a card leaves your hand its letter is assigned to the '
                'incoming card. ')
            usage.append('You reference your own '
                'hands via these letters, e.g. "!play C" or "!discard A". You '
                'can arrange your hand via !swap, !sort, and !move.')
            usage.append(
                'Hints are given by the !hint command. The hint format '
                'is "!hint nick color|number". Valid numbers are 1-5; '
                'valid colors are white, yellow, red, blue, or green.'
                ' Example: "!hint xyzzy blue" or "!hint fred 3"')
            usage.append(
                'The game continues until the deck is empty, all the cards '
                'are correcly displayed on the table, or the three storm '
                'tokens have been flipped.')
            for text, cmds in self.command_dict.iteritems():
                usage.append('%s commands: %s' % (text, ', '.join(cmds)))

            usage.append('Doing "!help [command]" will give details on that command.')
            self._to_nick(event, usage)
            return

        if args[0] in Hanabot._command_usage:
            self._to_nick(event, Hanabot._command_usage[args[0]])
        else:
            self._to_nick(event, 'No help for topic %s' % args[0])

    def handle_hint(self, args, event):
        log.debug('got hint event. args: %s', args)
        if not self._check_args(args, 2, [str, str], event, 'hint'):
            return 

        # now tell the engine about the !hint
        nick = event.source.nick
        self._display(self.games[event.target].hint_player(nick, player=args[0], hint=args[1]), event)

    def handle_rules(self, args, event):
        log.debug('got rules event. args: %s', args)
        if not self._check_args(args, 0, [], event, 'rules'):
            return 

        self._to_nick(event, 'Go here for english rules: '
                      'http://boardgamegeek.com/filepage/59655/hanabi-'
                      'english-translation')

    def _game_state(self, channel):
        pub, priv = [], []
        log.debug('game_state: chan: %s (%s), games: %s', channel, type(channel), self.games)
        if channel not in self.games:
            pub.append('There is no game being played in %s. '
                       'Use !new to start one while in %s.' % (channel, channel))
            return pub, priv

        game = self.games[channel]
        state = 'being played' if game.has_started() else 'waiting for players'
        if not game.has_started():
            if len(game.players()):
                ps = game.players()
                s = ('Waiting for players in %s. %d players have joined '
                     'so far: %s.' % (channel, len(ps), ', '.join(ps)))
            else:
                s = ('Waiting for players in %s, no players have '
                     'joined yet.' % channel)
        else:
            turn = game.turn()[0][0]
            s = ('Game is active and being played by players %s. %s' %
                 (', '.join(game.players()), turn))

        pub.append(s)
        return pub, priv

    def handle_game(self, args, event):
        log.debug('got game event. args: %s', args)
        if not self._check_args(args, 0, [], event, 'game'):
            return 

        self._display(self._game_state(event.target), event)

    def handle_games(self, args, event):
        log.debug('got games event. args: %s', args)
        if not self._check_args(args, 0, [], event, 'games'):
            return 

        # iterate over all channels the bot is in.
        for chan in self.channels.keys():
            self._display(self._game_state(str(chan)), event)

    def handle_turn(self, args, event):
        if not self._check_args(args, 0, [], event, 'turn'):
            return 

        self._display(self.games[event.target].turn(), event)

    def handle_turns(self, args, event):
        if not self._check_args(args, 0, [], event, 'turn'):
            return 

        self._display(self.games[event.target].turns(), event)

    def handle_table(self, args, event):
        log.debug('got table command.')
        if not self._check_args(args, 0, [], event, 'table'):
            return 

        self._display(self.games[event.target].get_table(), event)

    def handle_discard(self, args, event):
        log.debug('got discard event. args: %s', args)
        if not self._check_args(args, 1, [str], event, 'discard'):
            return 

        # discard the card and show the repsonse
        nick = event.source.nick
        self._display(self.games[event.target].discard_card(nick, args[0]), event)

        # discarding a card can trigger end game.
        if self.games[event.target].game_over():
            self.games[event.target] = None 

    def handle_play(self, args, event):
        log.debug('got play event. args: %s', args)
        # play the card and show the repsonse
        if not self._check_args(args, 1, [str], event, 'play'):
            return 

        nick = event.source.nick
        self._display(self.games[event.target].play_card(nick, args[0]), event)

        # tell the next player it is their turn.
        # take what would be public and make it privmsg
        pub, priv = self.games[event.target].turn()
        if len(pub):
            self._display(([], pub), event)

        # playing a card can trigger end game.
        if self.games[event.target].game_over():
            self.games[event.target] = None 
    
    def handle_hands(self, args, event):
        ''' Show hands of current game.  '''
        log.debug('got hands event. args: %s', args)
        if not self._check_args(args, 0, [], event, 'hands'):
            return 

        nick = event.source.nick
        self._display(self.games[event.target].get_hands(nick), event)

    def handle_xyzzy(self, args, event):
        self._to_nick(event, 'Nothing happens.')

    def handle_new(self, args, event):
        ''' Create a new game. '''
        log.debug('got new game event')

        if len(args) == 1:
            chan = '#%s' % args[0]
            self.connection.join(chan)
            self._to_chan(event, 'Hanabot joined channel %s. /join %s and !new '
                          'to begin game there.' % (chan, chan))
            return

        if not self._check_args(args, 0, [], event, 'new'):
            return 

        nick = event.source.nick
        if event.target in self.games:
            self._to_nick(event, 'There is already an active game in the channel.')
            return 
        
        log.info('Starting new game.')
        self.games[event.target] = Game()
        pub = ['New game started by %s. Accepting joins.' % nick]
        self._display((pub, []), event)

    def handle_join(self, args, event):
        '''join a game, if one is active.'''
        log.debug('got join event')
        if not self._check_args(args, 0, [], event, 'join'):
            return 

        nick = event.source.nick
        # enforce one game per player. Will not be needed if force users to 
        # send commands from the channel, so I can key the game to the channel.
        for chan, g in self.games.iteritems():
            if nick in g.players():
                msg = 'You are already in a game in %s. One game per nick please.' % chan
                self._to_nick(event, msg)
                return

        self._display(self.games[event.target].add_player(nick), event)

    # GTL TODO: make sure this is called when the players leaves the channel?
    def handle_leave(self, args, event):
        '''leave an active game.'''
        log.debug('got leave event. args: %s', args)
        if not self._check_args(args, 0, [], event, 'leave'):
            return 

        nick = event.source.nick
        # remove the player and display the result
        self._display(self.games[event.target].remove_player(nick), event)

        # removing a player can trigger end game (if there is now only one player).
        if self.games[event.target].game_over():
            self.games[event.target] = None

    def handle_sort(self, args, event):
        '''arg format: []'''
        log.debug('got handle_sort event. args: %s', args)
        if not self._check_args(args, 0, [], event, 'sort'):
            return 

        nick = event.source.nick
        self._display(self.games[event.target].sort_cards(nick), event)

    def handle_move(self, args, event):
        '''arg format: cardX slotN.'''
        log.debug('got handle_move event. args: %s', args)
        if not self._check_args(args, 2, [str, int], event, 'move'):
            return 

        nick = event.source.nick
        self._display(self.games[event.target].move_card(nick, args[0], args[1]), event)

    def handle_swap(self, args, event):
        '''arg format: cardA cardB.'''
        log.debug('got handle_swap event. args: %s', args)
        if not self._check_args(args, 2, [str, str], event, 'swap'):
            return 

        # do the swap
        nick = event.source.nick
        self._display(self.games[event.target].swap_cards(nick, args[0], args[1]), event)

    def handle_start(self, args, event):
        log.debug('got start event')
        if not self._check_args(args, 0, [], event, 'start'):
            return 

        nick = event.source.nick
        self._display(self.games[event.target].start_game(nick), event)

    def handle_part(self, args, event):
        log.debug('got part event')
        if not self._check_args(args, 0, [], event, 'part'):
            return 

        if event.target != self.initial_channel:
            self._to_chan(event, 'Hanabot leaving channel.')
            self.connection.part(event.target)
        else:
            self._to_chan(event, 'Hanabot refuses to leave home channel. Nice try.')

    def handle_delete(self, args, event):
        log.debug('got delete event')
        if not self._check_args(args, 0, [], event, 'delete'):
            return 

        del self.games[event.target]
        self._to_chan(event, '%s deleted game.' % event.source.nick)

    def handle_discardpile(self, args, event):
        log.debug('got discardpile event')
        if not self._check_args(args, 0, [], event, 'discardpile'):
            return 

        nick = event.source.nick
        self._display(self.games[event.target].get_discard_pile(), event)

    def _check_args(self, args, num, types, event, cmd):
        '''Check the given arguments for correct types and number. Show error
        message and help to nick on error and return False. Else return True. 
        As a side effect, set the types correctly. e.g. "1.2" is set to 1.2.'''
        if len(args) != num:
            self._to_nick(event, 'Wrong number of arguments to %s' % cmd)
            self.handle_help([cmd], event)
            return False
        elif len(types) != num:
            # This is an internal callee error, so no message. 
            log.info('internal error in _check_args: wrong number of types passed in.')
            return False

        for i in xrange(len(args)):
            try:
                args[i] = types[i](args[i])
            except ValueError:
                self._to_nick(event, 'Wrong type for argument %s in command %s.' % (args[i], cmd))
                self.handle_help([cmd], event)
                return False

        return True

    ####### static class data 
    _command_usage = {
        'new': '!new [channel] - create a new game. If channel is given, hanabot will join that channel. (Then use !new in that channel to create a new game there.)', 
        'delete': '!delete - delete a game.', 
        'join': '!join - join a game. If not game in channel, use !new to create one.', 
        'start': '!start - start a game. The game must have at least two players.',
        'leave': '!leave - leave a game. This is bad form.', 
        'part': '!part - tell Hanabot to part the channel. Note: Hanbot will not leave its home channel.', 
        'move': '!move card - move a card in your hand and slide all other cards "right". "card" must be one of A, B, C, D, or E. "index" is where to put the card, counting from the left and must be an integer between 1 and max hand size.',
        'swap': '!swap card card - swap cards in your hand. Card arguments must be one of A, B, C, D, or E.',
        'sort': '!sort - sort your cards into "correct" order, i.e. into ABCDE order from "mixed" state.', 
        'play': '!play card - play the card to the table. "card" must be one of A, B, C, D, or E.', 
        'hint': '!hint nick color|number - give a hint to a player about which color or number cards are in their hand. Valid colors: red, blue, white, green, yellow (or r, b, w, g, y) (case insensitive); valid numbers are 1, 2, 3, 4, or 5. Example "!hint frobozz blue" and "!hint plugh 4"',
        'discard': '!discard card - place a card in the discard pile. "card" must be one of A, B, C, D, or E.', 
        'help': 'Infinite recursion detected. Universe is rebooting...',
        'rules': '!rules - show URL for (english) Hanabi rules.', 
        'turn': '!turn - show which players turn it is.', 
        'turns': '!turns - show turn order in current play ordering.',
        'game': '!game - show the game state for current channel.', 
        'games': '!game - show game states for all channels hanabot has joined.',
        'hands': '!hands - show hands of players. Your own hand will be shown with the "backs" facing you, identified individually by a letter. When a card is removed the letter is reused for the new card.',
        'table': '!game - show the state of the table', 
        'discardpile': '!discardpile - show the current discard pile.',
        'grue': 'You are likely to be eaten.',
    }
