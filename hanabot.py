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
from hanabi import Game
from text_markup import irc_markup
from irc.bot import SingleServerIRCBot

log = logging.getLogger(__name__)


class Hanabot(SingleServerIRCBot):
    def __init__(self, server, channel, nick='hanabot', port=6667):
        log.debug('new bot started at %s:%d@#%s as %s', server, port,
                  channel, nick)
        SingleServerIRCBot.__init__(
            self,
            server_list=[(server, port)],
            nickname=nick,
            realname='Mumford J. Hanabot')

        # force channel to start with #
        self.channel = channel if channel[0] == '#' else '#%s' % channel

        # valid bot commands
        self.commands = ['status', 'start', 'delete', 'join', 'new', 'leave',
                         'move', 'help', 'play', 'turn', 'discard', 'hint',
                         'rules', 'games', 'list', 'st']
        self.admin_commands = ['die', 'show']

        # name ---> Game object dict
        self.games = {}
        self.markup = irc_markup()
        # when next() is called, a new non-repeating game name
        # is generated.
        self._game_ids = self._game_name_generator()

    # lib IRC callbacks
    #############################################################

    def on_nicknameinuse(self, conn, event):
        conn.nick(conn.get_nickname() + "_")

    def on_welcome(self, conn, event):
        conn.join(self.channel)

    def on_kick(self, conn, event):
        time.sleep(1)
        conn.join(self.channel)
        conn.notice(self.channel, 'Why I outta....')

    # GTL TODO: sort out and correctly parse public and private msgs.
    # the simple answer may be to just not allow private msgs.
    def on_privmsg(self, conn, event):
        log.debug('got privmsg. %s -> %s', event.source, event.arguments)
        self.parse_commands(event, event.arguments)

    def on_pubmsg(self, conn, event):
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

    def parse_commands(self, event, cmds):
        log.debug('got command. %s --> %s : %s',
                  event.source.nick, event.target, event.arguments)
        nick = event.source.nick

        # I don't understand when args will ever be more than just a string of
        # space separated words - need more IRC lib experience or docs.

        cmds = cmds[0].split()

        # op only commands - return after executing.
        if cmds[0] in self.admin_commands:
            log.debug('running admin cmd %s', cmds[0])
            for chname, chobj in self.channels.items():
                if nick in chobj.opers():
                    if cmds[0] == 'die':
                        self.die('Seppuku Successful')
                    elif cmds[0] == 'show':
                        for name, g in self.games.iteritems():
                            log.debug('Showing state for game %s', name)
                            self._display(g.show_game_state(), nick)

                    return

        # user commands
        if not cmds[0] in self.commands:
            self._to_nick(nick, 'My dearest brother Willis, I do not '
                          'understand this "%s" of which you speak.' %
                          ' '.join(cmds))
            return

        # call the appropriate handle_* function.
        method = getattr(self, 'handle_%s' % cmds[0], None)
        if method:
            method(cmds[1:], event)

    # some sugar for sending msgs
    def _display(self, output, nick):
        '''Output is the list of (public, private) msgs generated
        byt the Game engine. nick is the user to priv message.
        output == (string list, string list).
        __display assumes you want to send to self.channel.'''
        for l in output[0]:
            self.connection.notice(self.channel, l)

        for l in output[1]:
            self.connection.notice(nick, l)

    # some sugar for sending msgs
    def _to_chan(self, msgs):
        print 'sending to channel:', msgs
        if isinstance(msgs, list):
            self._display((msgs, []), None)
        elif isinstance(msgs, str):
            self._display(([msgs], []), None)

    # some sugar for sending strings
    def _to_nick(self, nick, msgs):
        if isinstance(msgs, list):
            self._display(([], msgs), nick)
        elif isinstance(msgs, str):
            self._display(([], [msgs]), nick)

    # Game Commands
    #############################################################
    def handle_help(self, args, event):
        log.debug('got help event. args: %s', args)
        usage = ['Below is the list of commands used during a game of Hanabi',
                 '. All commands end with an optional game id, used to ',
                 ' identify which game you are referencing. (The bot supports',
                 ' multiple, concurrent games. You do not need to give a game',
                 'id if there is only one game in the channel. ',
                 '------------',
                 'Your IRC client must display mIRC colors to play.',
                 '------------',
                 '!new [game id] - start a new game (named game id, if given).',
                 '!join [game id] - join a game. If no game id, join the single'
                 ' game running.',
                 '!start [game id] - start a game. The game must have at least '
                 'two players.', 
                 '!delete [game id] - delete a game.', 
                 '!leave [game id] - leave a game. This is bad form.',
                 '!move slotA slotB [game id] - move cards within your hand.', 
                 '!play slotN [game id] - play a card to the table.',
                 '!hint nick color|number slotA ... slotN - give a hint to a'
                 'player about which color or number cards are in their hand. ',
                 '!status [game id] - show game status.',
                 '!show [game id] - show all game status, including hands'
                 'and deck, (op only command.);',
                 '!games - show active games in channel, and their states.', 
                 '!rules - show URL for Hanabi rules.', 
                 '----------------------',
                 'Example !hint commands:', 
                 'Tell nick frobozz that he/she has red cards in slot 2 3:',
                 '!hint frobozz red 2 3',
                 'Tell nick xyzzy that he/she has the number 4 in slots 1 and 4', 
                 '!hint xyzzy 4 1 2 3',
                 'Valid colors are red, blue, white, green, yellow. Valid ',
                 'numbers are 1, 2, 3, 4, and 5.']
        self._to_nick(event.source.nick, usage)

    def handle_hint(self, args, event):
        log.debug('got hint event. args: %s', args)
        nick = event.source.nick

        if len(args) < 3:
            self._to_nick('bad !hint command. Must be of form !hint '
                          'nick color|number slotA, ... slotN')
            return
       
        # tricky - must figure out if last arg is a game id or a 
        # slot number.
        try:
            int(args[-1])
        except ValueError:
            game_name = args[-1]
            args = args[:-1]
        else:
            game_name = None

        game = self._get_game(game_name, nick)
        if not game:
            self._to_nick(nick, 'Unable to find game.')
            return
        
        try:
            cmd = int(args[1])
        except ValueError:
            try: 
                cmd = str(args[1])
            except ValueError:
                self._to_nick(nick, 'The hint command must be a string (color) or'
                                    ' an integer (card number).')
                return

        # convert slot numbers into list of ints.
        # args: nick color|number slotA ... slotN
        slots = list()
        for s in args[2:]:
            try:
                slots.append(int(s))
            except ValueError:
                self._to_nick('bad card slot value %s' % s)
                return

        # now hint the engine about the !hint
        self._display(game.hint_player(nick, args[0], cmd, slots), nick)


    def handle_rules(self, args, event):
        log.debug('got show rules event. args: %s', args)
        self._to_nick(event.source.nick, 'Go here for english rules: '
                      'http://boardgamegeek.com/filepage/59655/hanabi-'
                      'english-translation')

    def handle_list(self, args, event):
        self.handle_games(args, event)

    def handle_games(self, args, event):    
        log.debug('got games event. args: %s', args)
        if not len(self.games):
            self._to_nick(event.source.nick, 'No active games.')
            return
        
        nick = event.source.nick
        for name, game in self.games.iteritems():
            state = 'being played' if game.has_started() else 'waiting for players'
            if not game.has_started():
                turn = ''
            else:
                turn = game.turn(event.source.nick)[0][0]

            s = ('Game "%s": %s, %d players have joined. %s' %
                 (self.markup.bold(name), state, len(game.players), turn))
            self._to_nick(nick, s)

    def _get_game_and_slot(self, args, event):
        nick = event.source.nick
        if not (0 < len(args) < 3):
            self._to_nick(nick,'You must specify only a slot number (and '
                               'optionally a game id).')
            return (None, None)

        game_name = args[1] if len(args) == 2 else None
        game = self._get_game(game_name, nick)
        if not game:
            self._to_nick(nick, 'Unable to find game.')
            return (None, None)

        try:
            slot = int(args[0])
        except ValueError:
            self._to_nick(nick, 'Slot must be an integer.')
            return (None, None)

        if not (0 < slot < 6):
            self._to_nick(nick, 'Slot must be between 1 and 5.')
            return (None, None)

        return game, slot

    def handle_discard(self, args, event):
        log.debug('got discard event. args: %s', args)
        nick = event.source.nick
        game, slot = self._get_game_and_slot(args, event)
        if not game:
            return

        # discard the card and show the repsonse
        self._display(game.discard_card(nick, slot), nick)

        # discarding a card can trigger end game.
        if game.game_over():
            if game_name in self.games:
                del self.games[game_name] 
            elif len(self.games) == 1:   # GTL race condition here.
                self.games = {}

    def handle_play(self, args, event):
        log.debug('got play event. args: %s', args)
        nick = event.source.nick
        game, slot = self._get_game_and_slot(args, event)
        if not game:
            return

        # play the card and show the repsonse
        self._display(game.play_card(nick, slot), nick)

        # playing a card can trigger end game.
        if game.game_over():
            if game_name in self.games:
                del self.games[game_name] 
            elif len(self.games) == 1:   # GTL race condition here.
                self.games = {}
    
    def handle_st(self, args, event):
        self.handle_status(args, event)

    def handle_status(self, args, event):
        '''
        Show status of all/one of games user is playing in.
            args: [name]
        If game name is given, show just that game status.
        '''
        log.debug('got status event. args: %s', args)
        nick = event.source.nick
        if not len(self.games):
            self._to_nick(nick, 'There are no active games! You can start one'
                          ' with !new [game]')
            return

        game_name = None if len(args) == 0 else args[0]
        for name, g in self.games.iteritems():
            if g.in_game(nick):
                if (game_name and game_name == name) or not game_name:
                    self._display(g.get_status(nick), nick)

    def handle_new(self, args, event):
        '''
        Create a new game.
            args: [game name]
        If given, use the name as to id the game instance.
        '''
        log.debug('got new game event')
        game_name = None if len(args) == 0 else args[0]
        nick = event.source.nick
        if not game_name:
            game_name = self._game_ids.next()
        
        pub, priv = [], []
        if game_name in self.games.keys():
            priv.append('The game %s already exists.' %
                         self.markup.bold(game_name))
        else:
            log.info('Starting new game %s' % self.markup.bold(game_name))
            self.games[game_name] = Game(game_name, self.markup)
            pub.append('New game "%s" started by %s. Accepting joins '
                       'now.' % (self.markup.bold(game_name), nick))

        self._display((pub, priv), nick)

    def handle_join(self, args, event):
        '''args: [game]'''
        log.debug('got join event')

        nick = event.source.nick
        if not len(self.games):
            self._to_nick(nick, 'There are no games going on! Start one with '
                          '!new [name]')
            return

        if len(args) == 0 and len(self.games) > 1:
            self._to_nick(nick, 'You must specify a game via "!join game" as '
                          'there is more than one game going on.')
            return

        game_name = None if len(args) == 0 else args[0]
        game = self._get_game(game_name, nick)
        if not game:
            return

        self._display(game.add_player(event.source.nick), nick)

    # GTL TODO: make sure this is called when the players leaves the channel
    def handle_leave(self, args, event):
        '''args: game to leave. If not given leave all games.'''
        log.debug('got leave event. args: %s', args)
        nick = event.source.nick
        game_name = None if len(args) == 0 else args[0]
        if not game_name:
            # remove player from all games.
            for game in self.games.values():
                if game.in_game(nick):
                    self._display(game.remove_player(nick), nick)
            return

        game = self._get_game(game_name, nick)
        if not game:
            return

        self._display(game.remove_player(nick), nick)

    def handle_move(self, args, event):
        '''arg format: from_slot to_slot [game]'''
        log.debug('got handle_move event. args: %s', args)
        nick = event.source.nick
        if not (1 < len(args) < 4):
            self._to_nick(nick,  'Error in move cmd. Should be !move slotA '
                          'slotB [game]')
            return

        try:
            from_slot = int(args[0])
            to_slot = int(args[1])
        except ValueError:
            self._to_nick(nick, '!move args must be integers between 1 and 5.')
            return

        if not (0 < from_slot < 6) or not (0 < to_slot < 6):
            self._to_nick(nick, '!move args must be between 1 and 5.')
            return

        game_name = args[2] if len(args) == 3 else None
        game = self._get_game(game_name, nick)
        if not game:
            return

        # and finally do the move.
        self._display(game.move_card(nick, from_slot, to_slot), nick)

    def handle_start(self, args, event):
        log.debug('got start event')
        nick = event.source.nick
        game_name = None if len(args) == 0 else args[0]
        game = self._get_game(game_name, nick)
        if not game:
            return

        self._display(game.start_game(nick), nick)

    def handle_delete(self, args, event):
        log.debug('got delete event')
        nick = event.source.nick
        game_name = None if len(args) == 0 else args[0]
        game = self._get_game(game_name, nick)
        if not game:
            return
       
        if not game_name:
            game_name = self.games.keys()[0]

        del self.games[game_name]
        self._to_chan('Game %s deleted.' % self.markup.bold(game_name))

    def _get_game(self, name, nick):
        '''Given the name, find the referenced game. The name can be None
        in which case the first game is returned. If there are no games,
        None is returned. On error, a notice is sent to nick.'''

        # the cases:
        #   no games: fail no games running.
        #   no name given and only one game, return game else fail 'more
        #       than one game'
        #   name given: if found return game, else fail 'that game not found'
        if len(self.games) == 0:
            self._to_nick(nick, 'No games available. Start a one with !new '
                          '[gameID]')
            return None

        if not name:
            if len(self.games) == 1:
                return self.games[self.games.keys()[0]]
            else:
                self._to_nick(nick, 'More than one active game, specify which'
                              ' with the gameID')
                return None

        # at this point we know name is not None
        if name in self.games:
            log.debug('Found game %s for nick %s', name, nick)
            return self.games[name]
        else:
            self.connection.notice(nick, 'GameID %s not found.' %
                                   (self.markup.bold(name)))
            return None

    def _game_name_generator(self):
        # GTL TODO: make this into a pool instead of just a generator
        names = ['buffy', 'xander', 'willow', 'tara', 'anyanka', 'spike',
                 'giles', 'angel', 'mal', 'wash', 'simon', 'kaylee', 'zoe',
                 'river', 'book', 'inara', 'jayne', 'cordelia', 'oz', 'anya',
                 'dawn', 'the_master', 'drusilla', 'darla', 'the_mayor',
                 'adam', 'glory', 'joyce', 'jenny', 'wesley', 'harmony',
                 'kendra', 'olive', 'maisie']

        i = 0
        while True:
            random.shuffle(names)
            for n in names:
                if i == 0:
                    yield n
                else:
                    yield '%s_%d' % (n, i)
            else:
                i += 1
