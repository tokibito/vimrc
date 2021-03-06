# -*- coding: utf-8 -*-
"""
The Python parts of the Jedi library for VIM. It is mostly about communicating
with VIM.
"""

import json
import traceback  # for exception output
import re
import os
import platform
import subprocess
import sys
from shlex import split as shsplit
from contextlib import contextmanager
try:
    from itertools import zip_longest
except ImportError:
    from itertools import izip_longest as zip_longest  # Python 2


is_py3 = sys.version_info[0] >= 3
if is_py3:
    ELLIPSIS = "…"
    unicode = str
else:
    ELLIPSIS = u"…"


class PythonToVimStr(unicode):
    """ Vim has a different string implementation of single quotes """
    __slots__ = []

    def __new__(cls, obj, encoding='UTF-8'):
        if is_py3 or isinstance(obj, unicode):
            return unicode.__new__(cls, obj)
        else:
            return unicode.__new__(cls, obj, encoding)

    def __repr__(self):
        # this is totally stupid and makes no sense but vim/python unicode
        # support is pretty bad. don't ask how I came up with this... It just
        # works...
        # It seems to be related to that bug: http://bugs.python.org/issue5876
        if unicode is str:
            s = self
        else:
            s = self.encode('UTF-8')
        return '"%s"' % s.replace('\\', '\\\\').replace('"', r'\"')


class VimError(Exception):
    def __init__(self, message, throwpoint, executing):
        super(type(self), self).__init__(message)
        self.message = message
        self.throwpoint = throwpoint
        self.executing = executing

    def __str__(self):
        return self.message + '; created by: ' + repr(self.executing)


def _catch_exception(string, is_eval):
    """
    Interface between vim and python calls back to it.
    Necessary, because the exact error message is not given by `vim.error`.
    """
    e = 'jedi#_vim_exceptions(%s, %s)'
    result = vim.eval(e % (repr(PythonToVimStr(string, 'UTF-8')), is_eval))
    if 'exception' in result:
        raise VimError(result['exception'], result['throwpoint'], string)
    return result['result']


def vim_command(string):
    _catch_exception(string, 0)


def vim_eval(string):
    return _catch_exception(string, 1)


def no_jedi_warning(error=None):
    msg = "Please install Jedi if you want to use jedi-vim."
    if error:
        msg = '{} The error was: {}'.format(msg, error)
    vim.command('echohl WarningMsg'
                '| echom "Please install Jedi if you want to use jedi-vim."'
                '| echohl None')


def echo_highlight(msg):
    vim_command('echohl WarningMsg | echom "{}" | echohl None'.format(
        msg.replace('"', '\\"')))


import vim
try:
    import jedi
except ImportError as e:
    no_jedi_warning(str(e))
    jedi = None
else:
    try:
        version = jedi.__version__
    except Exception as e:  # e.g. AttributeError
        echo_highlight("Could not load jedi python module: {}".format(e))
        jedi = None
    else:
        if isinstance(version, str):
            # the normal use case, now.
            from jedi import utils
            version = utils.version_info()
        if version < (0, 7):
            echo_highlight('Please update your Jedi version, it is too old.')


def catch_and_print_exceptions(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (Exception, vim.error):
            print(traceback.format_exc())
            return None
    return wrapper


def _check_jedi_availability(show_error=False):
    def func_receiver(func):
        def wrapper(*args, **kwargs):
            if jedi is None:
                if show_error:
                    no_jedi_warning()
                return
            else:
                return func(*args, **kwargs)
        return wrapper
    return func_receiver


class JediRemote(object):
    python = 'python'
    remote_cmd = 'jedi_remote.py'

    def __init__(self):
        self._process = None

    def __del__(self):
        if self._process is not None:
            self._process.terminate()
            self._process = None

    def __getattr__(self, name):
        return (lambda *args, **kwargs: self._call(name, *args, **kwargs))

    @property
    def process(self):
        if not (self._process and self._process.poll() is None):
            cmd = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), self.remote_cmd)
            # On Windows platform, need STARTUPINFO
            if platform.system() == 'Windows':
                si = subprocess.STARTUPINFO()
                si.dwFlags = subprocess.STARTF_USESHOWWINDOW;
                si.wShowWindow = subprocess.SW_HIDE;
                stderr = subprocess.STDOUT
            else:
                si = None
                stderr = subprocess.PIPE
            self._process = subprocess.Popen(
                [self.python, cmd],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr,
                startupinfo=si,
            )

        return self._process

    def reload(self):
        if self._process is not None:
            self._process.terminate()
            self._process = None

    def _call(self, func, *args, **kwargs):
        data = json.dumps({'func': func, 'args': args, 'kwargs': kwargs})
        self.process.stdin.write(data.encode('utf-8'))
        self.process.stdin.write(b'\n')
        self.process.stdin.flush()

        ret = json.loads(self.process.stdout.readline().decode('utf-8'),
                         object_hook=ObjectDict)

        if ret['code'] == 'ok':
            return ret['return']

        elif ret['message'].startswith('jedi.api.NotFoundError'):
            raise jedi.NotFoundError()

        else:
            raise Exception(ret['message'])

@catch_and_print_exceptions
def set_script(source=None, column=None):
    jedi_remote.set_additional_dynamic_modules(
        [b.name for b in vim.buffers if b.name is not None and b.name.endswith('.py')])
    if source is None:
        source = '\n'.join(vim.current.buffer)
    row = vim.current.window.cursor[0]
    if column is None:
        column = vim.current.window.cursor[1]
    buf_path = vim.current.buffer.name
    encoding = vim_eval('&encoding') or 'latin1'
    jedi_remote.set_script(source, row, column, buf_path, encoding)


class ObjectDict(dict):
    def __getattr__(self, name):
        return self[name]

    def __setattr__(self, name, value):
        self[name] = value


jedi_remote = JediRemote()


@catch_and_print_exceptions
def get_script(source=None, column=None):
    jedi.settings.additional_dynamic_modules = \
        [b.name for b in vim.buffers if b.name is not None and b.name.endswith('.py')]
    if source is None:
        source = '\n'.join(vim.current.buffer)
    row = vim.current.window.cursor[0]
    if column is None:
        column = vim.current.window.cursor[1]
    buf_path = vim.current.buffer.name
    encoding = vim_eval('&encoding') or 'latin1'
    return jedi.Script(source, row, column, buf_path, encoding)


@_check_jedi_availability(show_error=False)
@catch_and_print_exceptions
def completions():
    row, column = vim.current.window.cursor
    # Clear call signatures in the buffer so they aren't seen by the completer.
    # Call signatures in the command line can stay.
    if vim_eval("g:jedi#show_call_signatures") == '1':
        clear_call_signatures()
    if vim.eval('a:findstart') == '1':
        count = 0
        for char in reversed(vim.current.line[:column]):
            if not re.match('[\w\d]', char):
                break
            count += 1
        vim.command('return %i' % (column - count))
    else:
        base = vim.eval('a:base')
        source = ''
        for i, line in enumerate(vim.current.buffer):
            # enter this path again, otherwise source would be incomplete
            if i == row - 1:
                source += line[:column] + base + line[column:]
            else:
                source += line
            source += '\n'
        # here again hacks, because jedi has a different interface than vim
        column += len(base)
        try:
            set_script(source=source, column=column)
            completions = jedi_remote.completions()
            signatures = jedi_remote.call_signatures()

            out = []
            for c in completions:
                d = dict(word=PythonToVimStr(c.name[:len(base)] + c.complete),
                         abbr=PythonToVimStr(c.name),
                         # stuff directly behind the completion
                         menu=PythonToVimStr(c.description),
                         info=PythonToVimStr(c.docstring),  # docstr
                         icase=1,  # case insensitive
                         dup=1  # allow duplicates (maybe later remove this)
                         )
                out.append(d)

            strout = str(out)
        except Exception:
            # print to stdout, will be in :messages
            print(traceback.format_exc())
            strout = ''
            completions = []
            signatures = []

        show_call_signatures(signatures)
        vim.command('return ' + strout)


@contextmanager
def tempfile(content):
    # Using this instead of the tempfile module because Windows won't read
    # from a file not yet written to disk
    with open(vim_eval('tempname()'), 'w') as f:
        f.write(content)
    try:
        yield f
    finally:
        os.unlink(f.name)

@_check_jedi_availability(show_error=True)
@catch_and_print_exceptions
def goto(mode="goto", no_output=False):
    """
    :param str mode: "related_name", "definition", "assignment", "auto"
    :return: list of definitions/assignments
    :rtype: list
    """
    set_script()
    try:
        if mode == "goto":
            definitions = [x for x in jedi_remote.goto_definitions()
                           if not x.in_builtin_module]
            if not definitions:
                definitions = jedi_remote.goto_assignments()
        elif mode == "related_name":
            definitions = jedi_remote.usages()
        elif mode == "definition":
            definitions = jedi_remote.goto_definitions()
        elif mode == "assignment":
            definitions = jedi_remote.goto_assignments()
    except jedi.NotFoundError:
        echo_highlight("Cannot follow nothing. Put your cursor on a valid name.")
        definitions = []
    else:
        if no_output:
            return definitions
        if not definitions:
            echo_highlight("Couldn't find any definitions for this.")
        elif len(definitions) == 1 and mode != "related_name":
            # just add some mark to add the current position to the jumplist.
            # this is ugly, because it overrides the mark for '`', so if anyone
            # has a better idea, let me know.
            vim_command('normal! m`')

            d = list(definitions)[0]
            if d.in_builtin_module:
                if d.is_keyword:
                    echo_highlight("Cannot get the definition of Python keywords.")
                else:
                    echo_highlight("Builtin modules cannot be displayed (%s)."
                                   % d.desc_with_module)
            else:
                using_tagstack = vim_eval('g:jedi#use_tag_stack') == '1'
                if d.module_path != vim.current.buffer.name:
                    result = new_buffer(d.module_path,
                                        using_tagstack=using_tagstack)
                    if not result:
                        return []
                if d.module_path and using_tagstack:
                    tagname = d.name
                    with tempfile('{0}\t{1}\t{2}'.format(tagname, d.module_path,
                            'call cursor({0}, {1})'.format(d.line, d.column + 1))) as f:
                        old_tags = vim.eval('&tags')
                        old_wildignore = vim.eval('&wildignore')
                        try:
                            # Clear wildignore to ensure tag file isn't ignored
                            vim.command('set wildignore=')
                            vim.command('let &tags = %s' %
                                        repr(PythonToVimStr(f.name)))
                            vim.command('tjump %s' % tagname)
                        finally:
                            vim.command('let &tags = %s' %
                                        repr(PythonToVimStr(old_tags)))
                            vim.command('let &wildignore = %s' %
                                        repr(PythonToVimStr(old_wildignore)))
                vim.current.window.cursor = d.line, d.column
        else:
            # multiple solutions
            lst = []
            for d in definitions:
                if d.in_builtin_module:
                    lst.append(dict(text=PythonToVimStr('Builtin ' + d.description)))
                else:
                    lst.append(dict(filename=PythonToVimStr(d.module_path),
                                    lnum=d.line, col=d.column + 1,
                                    text=PythonToVimStr(d.description)))
            vim_eval('setqflist(%s)' % repr(lst))
            vim_eval('jedi#add_goto_window(' + str(len(lst)) + ')')
    return definitions


@_check_jedi_availability(show_error=True)
@catch_and_print_exceptions
def show_documentation():
    set_script()
    try:
        definitions = jedi_remote.goto_definitions()
    except jedi.NotFoundError:
        definitions = []
    except Exception:
        # print to stdout, will be in :messages
        definitions = []
        print("Exception, this shouldn't happen.")
        print(traceback.format_exc())

    if not definitions:
        echo_highlight('No documentation found for that.')
        vim.command('return')
    else:
        docs = ['Docstring for %s\n%s\n%s' % (d.desc_with_module, '=' * 40, d.docstring)
                if d.docstring else '|No Docstring for %s|' % d for d in definitions]
        text = ('\n' + '-' * 79 + '\n').join(docs)
        vim.command('let l:doc = %s' % repr(PythonToVimStr(text)))
        vim.command('let l:doc_lines = %s' % len(text.split('\n')))
    return True


@catch_and_print_exceptions
def clear_call_signatures():
    # Check if using command line call signatures
    if vim_eval("g:jedi#show_call_signatures") == '2':
        vim_command('echo ""')
        return
    cursor = vim.current.window.cursor
    e = vim_eval('g:jedi#call_signature_escape')
    # We need two turns here to search and replace certain lines:
    # 1. Search for a line with a call signature and save the appended
    #    characters
    # 2. Actually replace the line and redo the status quo.
    py_regex = r'%sjedi=([0-9]+), (.*?)%s.*?%sjedi%s'.replace('%s', e)
    for i, line in enumerate(vim.current.buffer):
        match = re.search(py_regex, line)
        if match is not None:
            # Some signs were added to minimize syntax changes due to call
            # signatures. We have to remove them again. The number of them is
            # specified in `match.group(1)`.
            after = line[match.end() + int(match.group(1)):]
            line = line[:match.start()] + match.group(2) + after
            vim.current.buffer[i] = line
    vim.current.window.cursor = cursor


@_check_jedi_availability(show_error=False)
@catch_and_print_exceptions
def show_call_signatures(signatures=()):
    if vim_eval("has('conceal') && g:jedi#show_call_signatures") == '0':
        return

    if signatures == ():
        signatures = get_script().call_signatures()
    clear_call_signatures()

    if not signatures:
        return

    if vim_eval("g:jedi#show_call_signatures") == '2':
        return cmdline_call_signatures(signatures)

    for i, signature in enumerate(signatures):
        line, column = signature.bracket_start
        # signatures are listed above each other
        line_to_replace = line - i - 1
        # because there's a space before the bracket
        insert_column = column - 1
        if insert_column < 0 or line_to_replace <= 0:
            # Edge cases, when the call signature has no space on the screen.
            break

        # TODO check if completion menu is above or below
        line = vim_eval("getline(%s)" % line_to_replace)

        params = [p.description.replace('\n', '') for p in signature.params]
        try:
            # *_*PLACEHOLDER*_* makes something fat. See after/syntax file.
            params[signature.index] = '*_*%s*_*' % params[signature.index]
        except (IndexError, TypeError):
            pass

        # This stuff is reaaaaally a hack! I cannot stress enough, that
        # this is a stupid solution. But there is really no other yet.
        # There is no possibility in VIM to draw on the screen, but there
        # will be one (see :help todo Patch to access screen under Python.
        # (Marko Mahni, 2010 Jul 18))
        text = " (%s) " % ', '.join(params)
        text = ' ' * (insert_column - len(line)) + text
        end_column = insert_column + len(text) - 2  # -2 due to bold symbols

        # Need to decode it with utf8, because vim returns always a python 2
        # string even if it is unicode.
        e = vim_eval('g:jedi#call_signature_escape')
        if hasattr(e, 'decode'):
            e = e.decode('UTF-8')
        # replace line before with cursor
        regex = "xjedi=%sx%sxjedix".replace('x', e)

        prefix, replace = line[:insert_column], line[insert_column:end_column]

        # Check the replace stuff for strings, to append them
        # (don't want to break the syntax)
        regex_quotes = r'''\\*["']+'''
        # `add` are all the quotation marks.
        # join them with a space to avoid producing '''
        add = ' '.join(re.findall(regex_quotes, replace))
        # search backwards
        if add and replace[0] in ['"', "'"]:
            a = re.search(regex_quotes + '$', prefix)
            add = ('' if a is None else a.group(0)) + add

        tup = '%s, %s' % (len(add), replace)
        repl = prefix + (regex % (tup, text)) + add + line[end_column:]

        vim_eval('setline(%s, %s)' % (line_to_replace, repr(PythonToVimStr(repl))))


@catch_and_print_exceptions
def cmdline_call_signatures(signatures):
    def get_params(s):
        return [p.description.replace('\n', '') for p in s.params]

    def escape(string):
        return string.replace('"', '\\"').replace(r'\n', r'\\n')

    def join():
        return ', '.join(filter(None, (left, center, right)))

    def too_long():
        return len(join()) > max_msg_len

    if len(signatures) > 1:
        params = zip_longest(*map(get_params, signatures), fillvalue='_')
        params = ['(' + ', '.join(p) + ')' for p in params]
    else:
        params = get_params(signatures[0])

    index = next(iter(s.index for s in signatures if s.index is not None), None)

    # Allow 12 characters for showcmd plus 18 for ruler - setting
    # noruler/noshowcmd here causes incorrect undo history
    max_msg_len = int(vim_eval('&columns')) - 12
    if int(vim_eval('&ruler')):
        max_msg_len -= 18
    max_msg_len -= len(signatures[0].call_name) + 2  # call name + parentheses

    if max_msg_len < (1 if params else 0):
        return
    elif index is None:
        text = escape(', '.join(params))
        if params and len(text) > max_msg_len:
            text = ELLIPSIS
    elif max_msg_len < len(ELLIPSIS):
        return
    else:
        left = escape(', '.join(params[:index]))
        center = escape(params[index])
        right = escape(', '.join(params[index + 1:]))
        while too_long():
            if left and left != ELLIPSIS:
                left = ELLIPSIS
                continue
            if right and right != ELLIPSIS:
                right = ELLIPSIS
                continue
            if (left or right) and center != ELLIPSIS:
                left = right = None
                center = ELLIPSIS
                continue
            if too_long():
                # Should never reach here
                return

    max_num_spaces = max_msg_len
    if index is not None:
        max_num_spaces -= len(join())
    _, column = signatures[0].bracket_start
    spaces = min(int(vim_eval('g:jedi#first_col +'
                              'wincol() - col(".")')) +
                 column - len(signatures[0].call_name),
                 max_num_spaces) * ' '

    if index is not None:
        vim_command('                      echon "%s" | '
                    'echohl Function     | echon "%s" | '
                    'echohl None         | echon "("  | '
                    'echohl jediFunction | echon "%s" | '
                    'echohl jediFat      | echon "%s" | '
                    'echohl jediFunction | echon "%s" | '
                    'echohl None         | echon ")"'
                    % (spaces, signatures[0].call_name,
                       left + ', ' if left else '',
                       center, ', ' + right if right else ''))
    else:
        vim_command('                      echon "%s" | '
                    'echohl Function     | echon "%s" | '
                    'echohl None         | echon "(%s)"'
                    % (spaces, signatures[0].call_name, text))


@_check_jedi_availability(show_error=True)
@catch_and_print_exceptions
def rename():
    if not int(vim.eval('a:0')):
        vim_command('augroup jedi_rename')
        vim_command('autocmd InsertLeave <buffer> call jedi#rename(1)')
        vim_command('augroup END')

        vim_command("let s:jedi_replace_orig = expand('<cword>')")
        vim_command('normal! diw')
        vim_command("let s:jedi_changedtick = b:changedtick")
        vim_command('startinsert')

    else:
        # Remove autocommand.
        vim_command('autocmd! jedi_rename InsertLeave')

        # Get replacement, if there is something on the cursor.
        # This won't be the case when the user ends insert mode right away,
        # and `<cword>` would pick up the nearest word instead.
        if vim_eval('getline(".")[getpos(".")[2]-1]') != ' ':
            replace = vim_eval("expand('<cword>')")
        else:
            replace = None

        cursor = vim.current.window.cursor

        # Undo new word, but only if something was changed, which is not the
        # case when ending insert mode right away.
        if vim_eval('b:changedtick != s:jedi_changedtick') == '1':
            vim_command('normal! u')  # Undo new word.
        vim_command('normal! u')  # Undo diw.

        vim.current.window.cursor = cursor

        if replace:
            return do_rename(replace)


def rename_visual():
    replace = vim.eval('input("Rename to: ")')
    orig = vim.eval('getline(".")[(getpos("\'<")[2]-1):getpos("\'>")[2]]')
    do_rename(replace, orig)


def do_rename(replace, orig=None):
    if not len(replace):
        echo_highlight('No rename possible without name.')
        return

    if orig is None:
        orig = vim_eval('s:jedi_replace_orig')

    # Save original window / tab.
    saved_tab = int(vim_eval('tabpagenr()'))
    saved_win = int(vim_eval('winnr()'))

    temp_rename = goto(mode="related_name", no_output=True)
    # Sort the whole thing reverse (positions at the end of the line
    # must be first, because they move the stuff before the position).
    temp_rename = sorted(temp_rename, reverse=True,
                         key=lambda x: (x.module_path, x.start_pos))
    buffers = set()
    for r in temp_rename:
        if r.in_builtin_module:
            continue

        if os.path.abspath(vim.current.buffer.name) != r.module_path:
            result = new_buffer(r.module_path)
            if not result:
                echo_highlight("Jedi-vim: failed to create buffer window for {}!".format(r.module_path))
                continue

        buffers.add(vim.current.buffer.name)

        # Save view.
        saved_view = vim_eval('string(winsaveview())')

        # Replace original word.
        vim.current.window.cursor = r.start_pos
        vim_command('normal! c{:d}l{}'.format(len(orig), replace))

        # Restore view.
        vim_command('call winrestview(%s)' % saved_view)

    # Restore previous tab and window.
    vim_command('tabnext {:d}'.format(saved_tab))
    vim_command('{:d}wincmd w'.format(saved_win))

    if len(buffers) > 1:
        echo_highlight('Jedi did {:d} renames in {:d} buffers!'.format(
            len(temp_rename), len(buffers)))
    else:
        echo_highlight('Jedi did {:d} renames!'.format(len(temp_rename)))


@_check_jedi_availability(show_error=True)
@catch_and_print_exceptions
def py_import():
    # args are the same as for the :edit command
    args = shsplit(vim.eval('a:args'))
    import_path = args.pop()
    text = 'import %s' % import_path
    jedi_remote.set_script(text, 1, len(text), '')
    try:
        completion = jedi_remote.goto_assignments()[0]
    except IndexError:
        echo_highlight('Cannot find %s in sys.path!' % import_path)
    else:
        if completion.in_builtin_module:
            echo_highlight('%s is a builtin module.' % import_path)
        else:
            cmd_args = ' '.join([a.replace(' ', '\\ ') for a in args])
            new_buffer(completion.module_path, cmd_args)


@catch_and_print_exceptions
def py_import_completions():
    argl = vim.eval('a:argl')
    try:
        import jedi
    except ImportError:
        print('Pyimport completion requires jedi module: https://github.com/davidhalter/jedi')
        comps = []
    else:
        text = 'import %s' % argl
        jedi_remote.set_script(text, 1, len(text), '')
        comps = ['%s%s' % (argl, c.complete) for c in jedi_remote.completions()]
    vim.command("return '%s'" % '\n'.join(comps))


@catch_and_print_exceptions
def new_buffer(path, options='', using_tagstack=False):
    # options are what you can to edit the edit options
    if vim_eval('g:jedi#use_tabs_not_buffers') == '1':
        _tabnew(path, options)
    elif not vim_eval('g:jedi#use_splits_not_buffers') == '1':
        user_split_option = vim_eval('g:jedi#use_splits_not_buffers')
        split_options = {
            'top': 'topleft split',
            'left': 'topleft vsplit',
            'right': 'botright vsplit',
            'bottom': 'botright split',
            'winwidth': 'vs'
        }
        if user_split_option == 'winwidth' and vim.current.window.width <= 2 * int(vim_eval("&textwidth ? &textwidth : 80")):
            split_options['winwidth'] = 'sp'
        if user_split_option not in split_options:
            print('g:jedi#use_splits_not_buffers value is not correct, valid options are: %s' % ','.join(split_options.keys()))
        else:
            vim_command(split_options[user_split_option] + " %s" % escape_file_path(path))
    else:
        if vim_eval("!&hidden && &modified") == '1':
            if vim_eval("bufname('%')") is None:
                echo_highlight('Cannot open a new buffer, use `:set hidden` or save your buffer')
                return False
            else:
                vim_command('w')
        if using_tagstack:
            return True
        vim_command('edit %s %s' % (options, escape_file_path(path)))
    # sometimes syntax is being disabled and the filetype not set.
    if vim_eval('!exists("g:syntax_on")') == '1':
        vim_command('syntax enable')
    if vim_eval("&filetype != 'python'") == '1':
        vim_command('set filetype=python')
    return True


@catch_and_print_exceptions
def _tabnew(path, options=''):
    """
    Open a file in a new tab or switch to an existing one.

    :param options: `:tabnew` options, read vim help.
    """
    path = os.path.abspath(path)
    if vim_eval('has("gui")') == '1':
        vim_command('tab drop %s %s' % (options, escape_file_path(path)))
        return

    for tab_nr in range(int(vim_eval("tabpagenr('$')"))):
        for buf_nr in vim_eval("tabpagebuflist(%i + 1)" % tab_nr):
            buf_nr = int(buf_nr) - 1
            try:
                buf_path = vim.buffers[buf_nr].name
            except (LookupError, ValueError):
                # Just do good old asking for forgiveness.
                # don't know why this happens :-)
                pass
            else:
                if buf_path == path:
                    # tab exists, just switch to that tab
                    vim_command('tabfirst | tabnext %i' % (tab_nr + 1))
                    # Goto the buffer's window.
                    vim_command('exec bufwinnr(%i) . " wincmd w"' % (buf_nr + 1))
                    break
        else:
            continue
        break
    else:
        # tab doesn't exist, add a new one.
        vim_command('tabnew %s' % escape_file_path(path))


def escape_file_path(path):
    return path.replace(' ', r'\ ')


def print_to_stdout(level, str_out):
    print(str_out)
