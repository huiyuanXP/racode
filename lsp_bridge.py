"""
LSP bridge for symbol lookup and references.

Provides:
- Python: jedi for in-process symbol resolution
- TypeScript: ts-morph via Node.js subprocess
"""

import os
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import jedi
    JEDI_AVAILABLE = True
except ImportError:
    JEDI_AVAILABLE = False


class LSPBridge:
    """Bridge for LSP-based symbol lookup."""
    
    def __init__(self, project_root: str):
        """
        Initialize LSP bridge.
        
        Args:
            project_root: Root directory of the project
        """
        self.project_root = Path(project_root).resolve()
        self.ts_helper_path = Path(__file__).parent / "ts_helper.js"
    
    def get_python_references(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Find all references to a Python symbol using jedi.
        
        Args:
            symbol: Symbol name to find references for
            
        Returns:
            List of reference dictionaries with keys:
            - file_path, line, column, context, kind
        """
        if not JEDI_AVAILABLE:
            raise RuntimeError("jedi is not installed. Install with: pip install jedi")
        
        references = []
        
        # Search all Python files in the project
        for py_file in self.project_root.rglob('*.py'):
            # Skip virtual environments and cache directories
            if any(skip in py_file.parts for skip in {'.venv', 'venv', '__pycache__', 'node_modules'}):
                continue
            
            try:
                # Read file content
                content = py_file.read_text(encoding='utf-8')
                
                # Create jedi Script for this file
                script = jedi.Script(content, path=str(py_file))
                
                # Find all names in the file
                names = script.get_names(all_scopes=True, definitions=True, references=True)
                
                for name in names:
                    if name.name == symbol:
                        # Get context (line content)
                        lines = content.split('\n')
                        line_idx = name.line - 1
                        context = lines[line_idx].strip() if 0 <= line_idx < len(lines) else ""
                        
                        # Determine kind
                        kind = self._determine_python_kind(name)
                        
                        references.append({
                            'file_path': str(py_file.relative_to(self.project_root)),
                            'line': name.line,
                            'column': name.column,
                            'context': context,
                            'kind': kind
                        })
            except Exception:
                # Skip files that can't be processed
                continue
        
        return references
    
    def get_python_definition(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Find the definition of a Python symbol using jedi.
        
        Args:
            symbol: Symbol name to find definition for
            
        Returns:
            List of definition dictionaries (usually one) with keys:
            - file_path, line, column, context, kind
        """
        if not JEDI_AVAILABLE:
            raise RuntimeError("jedi is not installed. Install with: pip install jedi")
        
        definitions = []
        
        # Search all Python files in the project
        for py_file in self.project_root.rglob('*.py'):
            # Skip virtual environments and cache directories
            if any(skip in py_file.parts for skip in {'.venv', 'venv', '__pycache__', 'node_modules'}):
                continue
            
            try:
                # Read file content
                content = py_file.read_text(encoding='utf-8')
                
                # Create jedi Script for this file
                script = jedi.Script(content, path=str(py_file))
                
                # Find definitions
                names = script.get_names(all_scopes=True, definitions=True, references=False)
                
                for name in names:
                    if name.name == symbol and name.is_definition():
                        # Get context (line content)
                        lines = content.split('\n')
                        line_idx = name.line - 1
                        context = lines[line_idx].strip() if 0 <= line_idx < len(lines) else ""
                        
                        # Determine kind
                        kind = self._determine_python_kind(name)
                        
                        definitions.append({
                            'file_path': str(py_file.relative_to(self.project_root)),
                            'line': name.line,
                            'column': name.column,
                            'context': context,
                            'kind': kind
                        })
            except Exception:
                # Skip files that can't be processed
                continue
        
        return definitions
    
    def _determine_python_kind(self, name) -> str:
        """
        Determine the kind of a Python name.
        
        Args:
            name: jedi Name object
            
        Returns:
            Kind string (function, class, variable, etc.)
        """
        try:
            if name.type == 'function':
                return 'function_definition' if name.is_definition() else 'function_call'
            elif name.type == 'class':
                return 'class_definition' if name.is_definition() else 'class_reference'
            elif name.type == 'module':
                return 'module_import'
            elif name.type == 'param':
                return 'parameter'
            else:
                return 'variable'
        except Exception:
            return 'unknown'
    
    def get_typescript_references(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Find all references to a TypeScript symbol using ts-morph.
        
        Args:
            symbol: Symbol name to find references for
            
        Returns:
            List of reference dictionaries with keys:
            - file_path, line, column, context, kind
        """
        if not self.ts_helper_path.exists():
            raise RuntimeError(f"TypeScript helper not found: {self.ts_helper_path}")
        
        try:
            # Call ts_helper.js subprocess
            result = subprocess.run(
                ['node', str(self.ts_helper_path), 'references', str(self.project_root), symbol],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"TypeScript helper failed: {result.stderr}")
            
            # Parse JSON output
            references = json.loads(result.stdout)
            
            # Convert absolute paths to relative
            for ref in references:
                abs_path = Path(ref['file_path'])
                try:
                    ref['file_path'] = str(abs_path.relative_to(self.project_root))
                except ValueError:
                    # Path is outside project root, keep absolute
                    pass
            
            return references
            
        except subprocess.TimeoutExpired:
            raise RuntimeError("TypeScript helper timed out after 30 seconds")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse TypeScript helper output: {e}")
        except Exception as e:
            raise RuntimeError(f"TypeScript helper error: {e}")
    
    def get_typescript_definition(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Find the definition of a TypeScript symbol using ts-morph.
        
        Args:
            symbol: Symbol name to find definition for
            
        Returns:
            List of definition dictionaries (usually one) with keys:
            - file_path, line, column, context, kind
        """
        if not self.ts_helper_path.exists():
            raise RuntimeError(f"TypeScript helper not found: {self.ts_helper_path}")
        
        try:
            # Call ts_helper.js subprocess
            result = subprocess.run(
                ['node', str(self.ts_helper_path), 'definition', str(self.project_root), symbol],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"TypeScript helper failed: {result.stderr}")
            
            # Parse JSON output
            definitions = json.loads(result.stdout)
            
            # Convert absolute paths to relative
            for defn in definitions:
                abs_path = Path(defn['file_path'])
                try:
                    defn['file_path'] = str(abs_path.relative_to(self.project_root))
                except ValueError:
                    # Path is outside project root, keep absolute
                    pass
            
            return definitions
            
        except subprocess.TimeoutExpired:
            raise RuntimeError("TypeScript helper timed out after 30 seconds")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse TypeScript helper output: {e}")
        except Exception as e:
            raise RuntimeError(f"TypeScript helper error: {e}")
