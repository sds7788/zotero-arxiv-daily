"""Offline checks of the actual CLI control flow; no APIs or SMTP are used."""
import argparse
import ast
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


class DeliveryGuardTests(unittest.TestCase):
    def run_cli(self, flags, papers, send_empty=False):
        tree = ast.parse(Path('main.py').read_text())
        start = next(i for i, n in enumerate(tree.body)
                     if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'parser' for t in n.targets))
        tree.body = tree.body[start:]
        sender = Mock()
        renderer = Mock(return_value='<html>mock recommendations</html>')
        namespace = dict(__name__='__main__', argparse=argparse, os=os, sys=sys,
                         logger=Mock(), get_zotero_corpus=Mock(return_value=[{}]),
                         filter_corpus=Mock(), get_arxiv_paper=Mock(return_value=papers),
                         rerank_paper=Mock(return_value=papers), set_global_llm=Mock(),
                         render_email=renderer, send_email=sender)
        with patch.dict(os.environ, {'SEND_EMPTY': str(send_empty)}, clear=True), \
             patch.object(sys, 'argv', ['main.py'] + flags):
            try:
                exec(compile(tree, 'main.py', 'exec'), namespace)
            except SystemExit as e:
                self.assertEqual(e.code, 0)
        return sender, renderer

    def test_dry_run_with_recommendations_never_sends(self):
        sender, renderer = self.run_cli(['--dry-run'], [object()])
        renderer.assert_called_once()
        sender.assert_not_called()

    def test_dry_run_empty_email_never_sends(self):
        sender, renderer = self.run_cli(['--dry-run'], [], send_empty=True)
        renderer.assert_called_once()
        sender.assert_not_called()

    def test_normal_delivery_still_sends_once(self):
        sender, renderer = self.run_cli([], [object()])
        renderer.assert_called_once()
        sender.assert_called_once()


if __name__ == '__main__':
    unittest.main()
