"""Testes das skills `transcricao-video` e `criacao-site-blog`.

Não fazem chamadas reais de rede/CLI: `subprocess.run`, `Transcriber` e
`load_config` são mockados para validar apenas o contrato da skill (o que
ela escreve em `files/` e o que devolve em `AgentResult`).

Rodar com: python3 -m unittest tests.test_new_skills
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skills import criacao_site_blog, transcricao_video


class FakeConfig:
    groq_api_key = "fake-key"
    groq_transcribe_model = "whisper-large-v3"
    groq_language = "pt"
    claude_model = None


class TranscricaoVideoTest(unittest.TestCase):
    @patch("skills.transcricao_video.load_config", return_value=FakeConfig())
    @patch("skills.transcricao_video.Transcriber")
    @patch("skills.transcricao_video.subprocess.run")
    def test_transcribes_downloaded_audio(self, mock_run, mock_transcriber_cls, _mock_config):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        mock_transcriber_cls.return_value.transcribe.return_value = "texto transcrito"

        with self._tmp_working_dir() as working_dir:
            audio_path = working_dir / "files" / "audio.mp3"

            def fake_run(cmd, **kwargs):
                audio_path.parent.mkdir(parents=True, exist_ok=True)
                audio_path.write_bytes(b"fake-audio")
                return MagicMock(returncode=0, stderr="")

            mock_run.side_effect = fake_run

            result = transcricao_video.run({"url": "https://example.com/video"}, working_dir)

            self.assertTrue(result.success)
            self.assertEqual(result.result["texto"], "texto transcrito")
            self.assertTrue(Path(result.result["file"]).is_file())

    @patch("skills.transcricao_video.subprocess.run", side_effect=FileNotFoundError())
    def test_missing_yt_dlp_binary_fails_gracefully(self, _mock_run):
        with self._tmp_working_dir() as working_dir:
            result = transcricao_video.run({"url": "https://example.com/video"}, working_dir)
            self.assertFalse(result.success)
            self.assertIn("yt-dlp", result.error)

    def test_missing_url_fails_without_calling_subprocess(self):
        with self._tmp_working_dir() as working_dir:
            result = transcricao_video.run({}, working_dir)
            self.assertFalse(result.success)

    @staticmethod
    def _tmp_working_dir():
        import tempfile

        class _Ctx:
            def __enter__(self):
                self._tmp = tempfile.TemporaryDirectory()
                return Path(self._tmp.name)

            def __exit__(self, *exc):
                self._tmp.cleanup()

        return _Ctx()


class CriacaoSiteBlogTest(unittest.TestCase):
    @patch("skills.criacao_site_blog.load_config", return_value=FakeConfig())
    @patch("skills.criacao_site_blog.subprocess.run")
    def test_generates_and_zips_files(self, mock_run, _mock_config):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            working_dir = Path(tmp)

            def fake_run(cmd, cwd=None, **kwargs):
                (cwd / "index.html").write_text("<html></html>", encoding="utf-8")
                return MagicMock(returncode=0, stderr="")

            mock_run.side_effect = fake_run

            result = criacao_site_blog.run(
                {"tema": "cafeteria de bairro", "tipo": "landing page"}, working_dir
            )

            self.assertTrue(result.success)
            zip_path = Path(result.result["file"])
            self.assertTrue(zip_path.is_file())
            self.assertEqual(zip_path.suffix, ".zip")

    def test_missing_required_fields_fails_without_calling_subprocess(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            result = criacao_site_blog.run({"tema": "só tema"}, Path(tmp))
            self.assertFalse(result.success)

    @patch("skills.criacao_site_blog.load_config", return_value=FakeConfig())
    @patch("skills.criacao_site_blog.subprocess.run")
    def test_no_generated_files_fails(self, mock_run, _mock_config):
        import tempfile

        mock_run.return_value = MagicMock(returncode=0, stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            result = criacao_site_blog.run(
                {"tema": "tema", "tipo": "blog"}, Path(tmp)
            )
            self.assertFalse(result.success)


if __name__ == "__main__":
    unittest.main()
