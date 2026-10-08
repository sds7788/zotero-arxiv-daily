"""Offline regression checks: no credentials, models, network, or email."""
import argparse
import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import arxiv
import requests

import construct_email
import main
from network import HTTP_TIMEOUT, TimeoutSession
from paper import ArxivPaper


class RecoveryTests(unittest.TestCase):
    def test_dry_run_never_calls_sender(self):
        with patch.object(main, 'send_email') as send:
            main.deliver_email(argparse.Namespace(dry_run=True), '<html>preview</html>')
        send.assert_not_called()

    def test_false_cli_values_are_false(self):
        for value in ['false', 'False', '0']:
            self.assertFalse(main.parse_bool(value))
        with self.assertRaises(argparse.ArgumentTypeError):
            main.parse_bool('maybe')

    def test_arxiv_session_bounds_requests(self):
        with patch.object(requests.Session, 'request') as request:
            session = TimeoutSession()
            session.get('https://example.invalid')
            self.assertEqual(request.call_args.kwargs['timeout'], HTTP_TIMEOUT)
            session.get('https://example.invalid', timeout=5)
            self.assertEqual(request.call_args.kwargs['timeout'], 5)

    def test_invalid_feed_is_not_an_empty_day(self):
        response = MagicMock(content=b'<html>service unavailable</html>')
        with patch.object(main.requests, 'get', return_value=response):
            with self.assertRaisesRegex(RuntimeError, 'invalid Atom feed'):
                main.get_arxiv_paper('cs.AI')

    def test_source_503_is_optional(self):
        result = MagicMock()
        result.get_short_id.return_value = '2601.00001v1'
        result.download_source.side_effect = HTTPError('https://example.invalid', 503, 'Unavailable', {}, None)
        self.assertIsNone(ArxivPaper(result).tex)

    def test_enrichment_failure_still_renders_paper(self):
        class Paper:
            title = 'Offline example'
            summary = 'Fallback abstract'
            authors = [types.SimpleNamespace(name='Example Author')]
            score = 7
            arxiv_id = '2601.00001'
            pdf_url = 'https://arxiv.org/pdf/2601.00001'

            @property
            def code_url(self):
                raise ValueError('Malformed service response')

            @property
            def affiliations(self):
                raise TimeoutError()

            @property
            def tldr(self):
                raise TimeoutError()

        with patch.object(construct_email.time, 'sleep'):
            html = construct_email.render_email([Paper()])
        self.assertIn('Offline example', html)
        self.assertIn('Fallback abstract', html)
        self.assertIn('Unknown Affiliation', html)

    def test_failed_model_initialization_uses_abstract_without_retry(self):
        paper = ArxivPaper(types.SimpleNamespace(summary='Fallback abstract'))
        args = argparse.Namespace(use_llm_api=False, language='Chinese')
        with patch.object(main, 'set_global_llm', side_effect=TimeoutError()) as initialize:
            main.configure_llm(args, [paper])
            self.assertEqual(paper.tldr, 'Fallback abstract')
            self.assertIsNone(paper.affiliations)
        initialize.assert_called_once()

    def test_465_uses_ssl_directly_without_real_mail(self):
        with patch.object(construct_email.smtplib, 'SMTP_SSL') as ssl, patch.object(construct_email.smtplib, 'SMTP') as tls:
            construct_email.send_email('sender@example.invalid', 'receiver@example.invalid', 'dummy', 'example.invalid', 465, 'test')
        tls.assert_not_called()
        ssl.assert_called_once_with('example.invalid', 465, timeout=60)

    def test_587_uses_starttls_without_real_mail(self):
        with patch.object(construct_email.smtplib, 'SMTP') as tls, patch.object(construct_email.smtplib, 'SMTP_SSL') as ssl:
            construct_email.send_email('sender@example.invalid', 'receiver@example.invalid', 'dummy', 'example.invalid', 587, 'test')
        ssl.assert_not_called()
        tls.assert_called_once_with('example.invalid', 587, timeout=60)
        tls.return_value.starttls.assert_called_once()

    def test_complete_debug_dry_run_without_smtp_configuration(self):
        result = types.SimpleNamespace(
            title='Offline example', summary='Fallback abstract',
            authors=[types.SimpleNamespace(name='Example Author')],
            pdf_url='https://arxiv.org/pdf/2601.00001', links=[],
            get_short_id=lambda: '2601.00001v1',
            download_source=MagicMock(side_effect=HTTPError('https://example.invalid', 404, 'Missing', {}, None)),
        )
        zot = MagicMock()
        zot.everything.side_effect = [[], [{'data': {'abstractNote': 'Research interest', 'collections': []}}]]
        recommender = types.ModuleType('recommender')

        def rank(papers, corpus):
            for paper in papers:
                paper.score = 7
            return papers

        recommender.rerank_paper = MagicMock(side_effect=rank)
        llm = types.SimpleNamespace(lang='English', generate=MagicMock(return_value='Offline TLDR'))
        encoder = types.SimpleNamespace(encode=lambda s: [1], decode=lambda tokens: 'offline prompt')
        import llm as llm_module
        import paper as paper_module
        with patch.dict('os.environ', {'DRY_RUN': 'true', 'ZOTERO_ID': '123', 'ZOTERO_KEY': 'dummy'}, clear=True), \
             patch.object(sys, 'argv', ['main.py', '--debug']), \
             patch.dict(sys.modules, {'recommender': recommender}), \
             patch.object(main.zotero, 'Zotero', return_value=zot), \
             patch.object(arxiv.Client, 'results', return_value=iter([result] * 5)), \
             patch.object(llm_module, 'set_global_llm'), \
             patch.object(paper_module, 'get_llm', return_value=llm), \
             patch.object(paper_module.tiktoken, 'encoding_for_model', return_value=encoder), \
             patch.object(requests.Session, 'request', side_effect=AssertionError('Unexpected network')), \
             patch.object(construct_email.smtplib, 'SMTP', side_effect=AssertionError('Unexpected SMTP')) as smtp, \
             patch.object(construct_email.smtplib, 'SMTP_SSL', side_effect=AssertionError('Unexpected SMTP')) as ssl, \
             patch.object(construct_email.time, 'sleep'), \
             patch('socket.setdefaulttimeout'):
            runpy.run_path(str(Path(__file__).resolve().parents[1] / 'main.py'), run_name='__main__')
        smtp.assert_not_called()
        ssl.assert_not_called()
        self.assertEqual(llm.generate.call_count, 5)
        recommender.rerank_paper.assert_called_once()


if __name__ == '__main__':
    unittest.main()
