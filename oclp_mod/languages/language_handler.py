# oclp_mod/languages/language_handler.py
import json
from pathlib import Path
from typing import Dict, Optional
from .. import constants

class LanguageHandler:
    def __init__(self, constants: constants.Constants):
        self.constants = constants
        self.language_files = {
            "English": "en_US.json",
            "中文": "zh_CN.json",
            "Indonesia": "id_ID.json",
            "Spain": "es_ES.json"
        }
        self.current_language = constants.current_language
        self.translations = self._load_language_file()

    def _load_language_file(self) -> Dict[str, str]:
        """Load the appropriate language file based on current setting"""
        lang_file = self.language_files.get(self.current_language, "id_ID.json")
        lang_path = Path(__file__).parent.parent / "languages" / lang_file
        
        try:
            with open(lang_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading language file: {e}")
            return {}

    def set_language(self, language: str) -> bool:
        """Change the application language"""
        if language in self.language_files:
            self.current_language = language
            self.constants.current_language = language
            self.translations = self._load_language_file()
            return True
        return False

    def get_translation(self, key: str, default: Optional[str] = None) -> str:
        """Get a translation for the given key"""
        return self.translations.get(key, default or key)
