"""Versioned small-edit author capability. No model calls or candidate execution.

No full-file replacement tool: edits reference a current file SHA and exact line
slice SHA, with at most24 removed lines and1600 inserted UTF-8 bytes. This byte
cap does not guarantee a generated JSON envelope fits1024tokens. Output limits
and failures must still be enforced by an independently frozen author runner.
"""
import hashlib
import json
from pathlib import Path
from skill_rsi_author_loop import AuthorEdits, tool, NAME, REV, TEXT
from skill_rsi_author_workspace import OUTPUTS

sha = lambda data: hashlib.sha256(data).hexdigest()
INT = {'type': 'integer', 'minimum': 1}
TOOLS = [tool('read_lines', {'name': NAME, 'start': INT,
         'count': {'type': 'integer', 'minimum': 1, 'maximum': 24}}, ['name','start','count']),
         tool('edit_lines', {'name': NAME, 'expected_sha256': REV, 'start': INT,
         'delete_count': {'type': 'integer', 'minimum': 0, 'maximum': 24},
         'expected_slice_sha256': TEXT, 'text': TEXT},
         ['name','expected_sha256','start','delete_count','expected_slice_sha256','text']),
         tool('finish', {}, [])]


class SmallEdits(AuthorEdits):
    def __init__(self, root, resources):
        super().__init__(root, resources)
        self.requests = 0

    def current(self, name):
        if name not in OUTPUTS:
            raise ValueError('output capability')
        w = self.workspace
        if any(p.is_symlink() for p in (w.root, w.root/'output', w.root/'output'/name)):
            raise ValueError('symlink refused')
        path = w.root/'output'/name
        data = path.read_bytes() if name in w.state else b''
        if name not in w.state and path.exists():
            raise ValueError('untracked file')
        if name in w.state and sha(data) != w.state[name]:
            raise ValueError('external change')
        return data.decode().splitlines(keepends=True)

    def dispatch(self, name, args):
        if self.requests >= 24 or self.finished:
            raise ValueError('author operation budget or submitted')
        self.requests += 1
        receipt = {'index': self.requests, 'tool': name, 'args': args}
        try:
            if name == 'finish':
                result = super().dispatch(name, args)
            elif name == 'read_lines':
                if set(args) != {'name','start','count'}:
                    raise ValueError('read fields')
                lines = self.current(args['name'])
                start, count = args['start'], args['count']
                if type(start) is not int or type(count) is not int or not 1 <= start <= len(lines)+1 or not 1 <= count <= 24:
                    raise ValueError('line range')
                text = ''.join(lines[start-1:start-1+count])
                if len(text.encode()) > 3200:
                    raise ValueError('read byte cap; choose smaller range')
                result = {'name': args['name'], 'start': start, 'line_count': len(lines),
                          'returned_lines': len(lines[start-1:start-1+count]),
                          'text': text, 'slice_sha256': sha(text.encode()),
                          'sha256': self.workspace.state.get(args['name'])}
            elif name == 'edit_lines':
                if set(args) != {'name','expected_sha256','start','delete_count','expected_slice_sha256','text'}:
                    raise ValueError('edit fields')
                lines = self.current(args['name'])
                if args['expected_sha256'] != self.workspace.state.get(args['name']):
                    raise ValueError('stale revision')
                start, count, text = args['start'], args['delete_count'], args['text']
                if type(start) is not int or type(count) is not int or not 1 <= start <= len(lines)+1 or not 0 <= count <= 24 or start-1+count > len(lines):
                    raise ValueError('edit range')
                if not isinstance(text,str) or len(text.encode()) > 1600:
                    raise ValueError('insert byte cap')
                old = ''.join(lines[start-1:start-1+count])
                if sha(old.encode()) != args['expected_slice_sha256']:
                    raise ValueError('slice changed')
                content = ''.join(lines[:start-1]) + text + ''.join(lines[start-1+count:])
                # Exact supplied bytes only: no newline, indentation or syntax repair.
                result = self.workspace.dispatch({'op':'write','name':args['name'],
                         'expected_sha256':args['expected_sha256'],'content':content})
            else:
                raise ValueError('ungranted tool')
            receipt['result'] = result
            return result
        except BaseException as error:
            receipt['error'] = type(error).__name__ + ':' + str(error)
            raise
        finally:
            with (self.workspace.root/'small-edit-events.jsonl').open('a') as f:
                f.write(json.dumps(receipt, ensure_ascii=False)+'\n')
