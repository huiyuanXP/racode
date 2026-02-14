#!/usr/bin/env node
/**
 * TypeScript LSP Helper using ts-morph
 * 
 * Usage:
 *   node ts_helper.js references <project_root> <symbol>
 *   node ts_helper.js definition <project_root> <symbol>
 * 
 * Output: JSON array of results
 */

const { Project } = require('ts-morph');
const path = require('path');
const fs = require('fs');

// Parse command line arguments
const [,, command, projectRoot, symbol] = process.argv;

if (!command || !projectRoot || !symbol) {
  console.error('Usage: node ts_helper.js <references|definition> <project_root> <symbol>');
  process.exit(1);
}

// Initialize ts-morph project
const project = new Project({
  tsConfigFilePath: findTsConfig(projectRoot),
  skipAddingFilesFromTsConfig: false,
  skipFileDependencyResolution: true
});

// Add all TypeScript files if no tsconfig found
if (!project.getCompilerOptions()) {
  const tsFiles = findTypeScriptFiles(projectRoot);
  project.addSourceFilesAtPaths(tsFiles);
}

/**
 * Find tsconfig.json in project root or parent directories
 */
function findTsConfig(startPath) {
  let currentPath = path.resolve(startPath);
  
  while (currentPath !== path.parse(currentPath).root) {
    const tsConfigPath = path.join(currentPath, 'tsconfig.json');
    if (fs.existsSync(tsConfigPath)) {
      return tsConfigPath;
    }
    currentPath = path.dirname(currentPath);
  }
  
  return undefined;
}

/**
 * Recursively find all TypeScript files in directory
 */
function findTypeScriptFiles(dir) {
  const files = [];
  const skipDirs = new Set(['node_modules', '.git', 'dist', 'build', '.next', 'coverage']);
  
  function walk(currentDir) {
    const entries = fs.readdirSync(currentDir, { withFileTypes: true });
    
    for (const entry of entries) {
      const fullPath = path.join(currentDir, entry.name);
      
      if (entry.isDirectory()) {
        if (!skipDirs.has(entry.name)) {
          walk(fullPath);
        }
      } else if (entry.isFile()) {
        const ext = path.extname(entry.name);
        if (['.ts', '.tsx', '.js', '.jsx'].includes(ext)) {
          files.push(fullPath);
        }
      }
    }
  }
  
  walk(dir);
  return files;
}

/**
 * Get context line from source file
 */
function getContext(sourceFile, line) {
  const lines = sourceFile.getFullText().split('\n');
  return lines[line - 1]?.trim() || '';
}

/**
 * Determine the kind of a node
 */
function getNodeKind(node) {
  const kindName = node.getKindName();
  
  if (kindName.includes('FunctionDeclaration') || kindName.includes('FunctionExpression')) {
    return 'function_definition';
  } else if (kindName.includes('ClassDeclaration')) {
    return 'class_definition';
  } else if (kindName.includes('InterfaceDeclaration')) {
    return 'interface_definition';
  } else if (kindName.includes('TypeAliasDeclaration')) {
    return 'type_definition';
  } else if (kindName.includes('VariableDeclaration')) {
    return 'variable_definition';
  } else if (kindName.includes('CallExpression')) {
    return 'function_call';
  } else if (kindName.includes('Identifier')) {
    return 'reference';
  } else {
    return 'unknown';
  }
}

/**
 * Find references to a symbol
 */
function findReferences(symbol) {
  const results = [];
  const sourceFiles = project.getSourceFiles();
  
  for (const sourceFile of sourceFiles) {
    // Find all identifiers with matching name
    const identifiers = sourceFile.getDescendantsOfKind(require('ts-morph').SyntaxKind.Identifier);
    
    for (const identifier of identifiers) {
      if (identifier.getText() === symbol) {
        const pos = identifier.getStartLinePos();
        const line = sourceFile.getLineAndColumnAtPos(pos).line;
        const column = sourceFile.getLineAndColumnAtPos(pos).column;
        
        results.push({
          file_path: sourceFile.getFilePath(),
          line: line,
          column: column,
          context: getContext(sourceFile, line),
          kind: getNodeKind(identifier.getParent())
        });
      }
    }
  }
  
  return results;
}

/**
 * Find definition of a symbol
 */
function findDefinition(symbol) {
  const results = [];
  const sourceFiles = project.getSourceFiles();
  
  for (const sourceFile of sourceFiles) {
    // Find function declarations
    const functions = sourceFile.getFunctions();
    for (const func of functions) {
      if (func.getName() === symbol) {
        const pos = func.getStartLinePos();
        const line = sourceFile.getLineAndColumnAtPos(pos).line;
        const column = sourceFile.getLineAndColumnAtPos(pos).column;
        
        results.push({
          file_path: sourceFile.getFilePath(),
          line: line,
          column: column,
          context: getContext(sourceFile, line),
          kind: 'function_definition'
        });
      }
    }
    
    // Find class declarations
    const classes = sourceFile.getClasses();
    for (const cls of classes) {
      if (cls.getName() === symbol) {
        const pos = cls.getStartLinePos();
        const line = sourceFile.getLineAndColumnAtPos(pos).line;
        const column = sourceFile.getLineAndColumnAtPos(pos).column;
        
        results.push({
          file_path: sourceFile.getFilePath(),
          line: line,
          column: column,
          context: getContext(sourceFile, line),
          kind: 'class_definition'
        });
      }
    }
    
    // Find interface declarations
    const interfaces = sourceFile.getInterfaces();
    for (const iface of interfaces) {
      if (iface.getName() === symbol) {
        const pos = iface.getStartLinePos();
        const line = sourceFile.getLineAndColumnAtPos(pos).line;
        const column = sourceFile.getLineAndColumnAtPos(pos).column;
        
        results.push({
          file_path: sourceFile.getFilePath(),
          line: line,
          column: column,
          context: getContext(sourceFile, line),
          kind: 'interface_definition'
        });
      }
    }
    
    // Find type alias declarations
    const typeAliases = sourceFile.getTypeAliases();
    for (const typeAlias of typeAliases) {
      if (typeAlias.getName() === symbol) {
        const pos = typeAlias.getStartLinePos();
        const line = sourceFile.getLineAndColumnAtPos(pos).line;
        const column = sourceFile.getLineAndColumnAtPos(pos).column;
        
        results.push({
          file_path: sourceFile.getFilePath(),
          line: line,
          column: column,
          context: getContext(sourceFile, line),
          kind: 'type_definition'
        });
      }
    }
    
    // Find variable declarations (including const arrow functions)
    const variables = sourceFile.getVariableDeclarations();
    for (const variable of variables) {
      if (variable.getName() === symbol) {
        const pos = variable.getStartLinePos();
        const line = sourceFile.getLineAndColumnAtPos(pos).line;
        const column = sourceFile.getLineAndColumnAtPos(pos).column;
        
        results.push({
          file_path: sourceFile.getFilePath(),
          line: line,
          column: column,
          context: getContext(sourceFile, line),
          kind: 'variable_definition'
        });
      }
    }
  }
  
  return results;
}

// Execute command
try {
  let results;
  
  if (command === 'references') {
    results = findReferences(symbol);
  } else if (command === 'definition') {
    results = findDefinition(symbol);
  } else {
    console.error(`Unknown command: ${command}`);
    process.exit(1);
  }
  
  // Output JSON
  console.log(JSON.stringify(results, null, 2));
  
} catch (error) {
  console.error(`Error: ${error.message}`);
  process.exit(1);
}
