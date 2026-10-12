"""
SolidWorks MCP Configuration
----------------------------
Configuration management with JSON file support.
"""

import json
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class SolidWorksConfig:
    """
    Configurazione del server (solidworks_mcp/config.json). Solo le chiavi lette davvero dal codice:
        exe_path: percorso di SLDWORKS.exe ("auto" = ricerca automatica)
        startup_timeout: secondi di attesa all'avvio di SolidWorks
        connection_retry_interval: secondi fra due tentativi di connessione durante l'avvio
        default_unit: unita' predefinita delle quote (mm, cm, m, inch, ft)
        log_level: DEBUG, INFO, WARNING, ERROR
        log_file: nome del file di log (nella cartella del pacchetto)
    I template di pezzo/assieme/disegno non si configurano: li chiede a SolidWorks (Opzioni > Modelli predefiniti).
    """

    exe_path: str = "auto"
    startup_timeout: int = 120
    connection_retry_interval: int = 5
    default_unit: str = "mm"
    log_level: str = "INFO"
    log_file: str = "solidworks_mcp.log"

    def __post_init__(self):
        """Validate configuration after initialization"""
        valid_units = ["mm", "inch", "m", "cm", "ft"]
        if self.default_unit not in valid_units:
            logger.warning(f"Invalid unit '{self.default_unit}', using 'mm'")
            self.default_unit = "mm"
        
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level.upper() not in valid_levels:
            logger.warning(f"Invalid log level '{self.log_level}', using 'INFO'")
            self.log_level = "INFO"
    
    @classmethod
    def get_config_path(cls) -> Path:
        """Get default config file path"""
        return Path(__file__).parent / "config.json"
    
    @classmethod
    def load(cls, config_path: Optional[str] = None) -> 'SolidWorksConfig':
        """
        Load configuration from JSON file
        
        Args:
            config_path: Path to config file (uses default if None)
        
        Returns:
            SolidWorksConfig instance
        """
        if config_path is None:
            config_path = cls.get_config_path()
        else:
            config_path = Path(config_path)
        
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info(f"Loaded config from: {config_path}")
                known = set(cls.__dataclass_fields__)
                unknown = sorted(set(data) - known)
                if unknown:                 # chiavi vecchie o sbagliate: ignorate, non fanno perdere le altre
                    logger.warning(f"Config: chiavi ignorate {unknown}")
                return cls(**{k: v for k, v in data.items() if k in known})
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in config file: {e}")
            except TypeError as e:
                logger.error(f"Invalid config structure: {e}")
        
        logger.info("Using default configuration")
        return cls()
    
    def save(self, config_path: Optional[str] = None) -> bool:
        """
        Save configuration to JSON file
        
        Args:
            config_path: Path to save config (uses default if None)
        
        Returns:
            True if successful
        """
        if config_path is None:
            config_path = self.get_config_path()
        else:
            config_path = Path(config_path)
        
        try:
            # Ensure directory exists
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(asdict(self), f, indent=2)
            
            logger.info(f"Saved config to: {config_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary"""
        return asdict(self)
    
    def update(self, **kwargs) -> None:
        """Update configuration values"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
                logger.debug(f"Config updated: {key} = {value}")
            else:
                logger.warning(f"Unknown config key: {key}")
    
    def get_log_level_int(self) -> int:
        """Get logging level as integer"""
        levels = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        return levels.get(self.log_level.upper(), logging.INFO)


# ============================================================================
# Global Configuration Instance
# ============================================================================

# Load config on module import
config = SolidWorksConfig.load()


def get_config() -> SolidWorksConfig:
    """Get global configuration instance"""
    return config


def reload_config(config_path: Optional[str] = None) -> SolidWorksConfig:
    """Reload configuration from file"""
    global config
    config = SolidWorksConfig.load(config_path)
    return config


def save_config(config_path: Optional[str] = None) -> bool:
    """Save current configuration to file"""
    return config.save(config_path)
