from functools import partial
import markdown2
import os
import pygit2 as git
from collections import namedtuple
import jinja2


_templates = None
_md = partial(markdown2.markdown, extras=['fenced-code-blocks'])
def templates():
    global _templates
    if _templates is None:
        loader = jinja2.FileSystemLoader(os.path.dirname(__file__))
        env = jinja2.Environment(loader=loader)
        env.filters['as_html_fragment'] = as_html_fragment
        env.filters['diff_line_classification'] = Diff.line_classification
        env.filters['suppress_no_lineno'] = Diff.suppress_no_lineno
        env.filters['markdown'] = lambda text: jinja2.Markup(_md(text))
        _templates = {'node': env.get_template('node.html.tmpl'),
                      'content': env.get_template('content.html.tmpl'),
                      'diff': env.get_template('diff.html.tmpl'),
                      'page': env.get_template('page.html.tmpl')}
    return _templates

"""Possible approach to marginal links to tree/commit:

<div style="position:relative"><h2 style="box-sizing:border-box;position:absolute;bottom:-16px;right:0px;padding-right:16px">[TREE]</h2><h2>draw_alien(): Add</h2></div>
"""

def as_html_fragment(x):
    return x.as_html_fragment()


def _commit(repo, oid, required_n_parents=None, tag=None):
    commit = repo[oid]
    if not isinstance(commit, git.Commit):
        raise ValueError('not a Commit')
    parent_ids = commit.parent_ids
    n_parents = len(parent_ids)
    if required_n_parents is not None and n_parents != required_n_parents:
        raise ValueError('commit {} has {} parent/s so is not a {}'
                         .format(oid, n_parents, tag))
    return commit


class Node:
    def as_html_fragment(self):
        # TODO: Add 'level' argument?
        return templates()['node'].render(node=self)

    @property
    def title(self):
        return self.commit.message.split('\n')[0]

    @property
    def message_body(self):
        return '\n'.join(self.commit.message.split('\n')[1:])

    @property
    def diff(self):
        return Diff(self.repo, self.commit.tree.oid, self.commit.parents[0].tree.oid)


class LeafCommit(namedtuple('LeafCommit', 'repo commit depth'), Node):
    @classmethod
    def from_commit(cls, repo, oid, depth):
        commit = _commit(repo, oid, 1, 'leaf-commit')
        return cls(repo, commit, depth)


class SectionCommit(namedtuple('SectionCommit', 'repo commit children depth'), Node):
    @classmethod
    def from_branch(cls, repo, branch_name, depth):
        return cls.from_commit(repo, repo.lookup_branch(branch_name).target, depth)

    @classmethod
    def from_commit(cls, repo, oid, depth):
        commit = _commit(repo, oid, 2, 'section-commit')
        prev_node = commit.parent_ids[0]
        ch = commit.parent_ids[1]
        children = []
        while ch != prev_node:
            children.append(leaf_or_section(repo, ch, depth + 1))
            ch = repo[ch].parent_ids[0]
        children.reverse()
        return cls(repo, commit, children, depth)


class Diff(namedtuple('Diff', 'repo tree_1 tree_0')):
    def as_html_fragment(self):
        diff = self.repo.diff(self.repo[self.tree_0], self.repo[self.tree_1])
        return templates()['diff'].render(diff=diff)

    @staticmethod
    def line_classification(line):
        if line.old_lineno == -1:
            return 'diff-add'
        elif line.new_lineno == -1:
            return 'diff-del'
        else:
            return 'diff-unch'

    @staticmethod
    def suppress_no_lineno(lineno):
        if lineno == -1:
            return ''
        return str(lineno)

def leaf_or_section(repo, oid, depth):
    commit = _commit(repo, oid)
    n_parents = len(commit.parent_ids)
    if n_parents == 1:
        return LeafCommit.from_commit(repo, oid, depth)
    elif n_parents == 2:
        return SectionCommit.from_commit(repo, oid, depth)
    else:
        raise ValueError('cannot handle {} parents of {}'
                         .format(n_parents, oid))


def list_from_range(repo, base_branch_name, branch_name):
    end_oid = repo.lookup_branch(base_branch_name).target
    oid = repo.lookup_branch(branch_name).target
    elements = []
    while oid != end_oid:
        element = leaf_or_section(repo, oid, 0)
        elements.append(element)
        oid = element.commit.parent_ids[0]
    elements.reverse()
    return elements


def render(nodes):
    content = templates()['content'].render(nodes=nodes)
    print(templates()['page'].render(content=content))
