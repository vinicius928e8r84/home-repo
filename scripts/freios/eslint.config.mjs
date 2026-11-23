import { readFileSync } from 'node:fs';
import globals from 'globals';
import tsParser from '@typescript-eslint/parser';

const ignorar = JSON.parse(readFileSync(new URL('./ignorar.json', import.meta.url), 'utf8'))
  .filter(item => item.ferramentas.includes('eslint'))
  .map(item => item.glob);

const correcao = {
  'no-undef': 'error',
  'no-unused-vars': ['error', { args: 'none', caughtErrors: 'none', ignoreRestSiblings: true }],
  'no-unreachable': 'error',
  'no-dupe-keys': 'error',
  'no-dupe-else-if': 'error',
  'no-dupe-args': 'error',
  'no-duplicate-case': 'error',
  'no-func-assign': 'error',
  'no-self-assign': 'error',
  'no-unsafe-finally': 'error',
  'no-unsafe-negation': 'error',
  'no-cond-assign': ['error', 'except-parens'],
  'no-empty': ['error', { allowEmptyCatch: true }],
  'no-ex-assign': 'error',
  'no-const-assign': 'error',
  'no-import-assign': 'error',
  'no-sparse-arrays': 'error',
  'no-useless-catch': 'error',
  'use-isnan': 'error',
  'valid-typeof': 'error',
  eqeqeq: ['error', 'always', { null: 'ignore' }],
  'no-throw-literal': 'error',
};

const saude = {
  complexity: ['error', 8],
  'max-depth': ['error', 3],
  'max-params': ['error', 4],
  'max-lines-per-function': ['error', { max: 69, skipBlankLines: true, skipComments: true }],
};

const extensoesDoPi = {
  'no-console': 'error',
  'no-debugger': 'error',
};

const opcoes = { noInlineConfig: true };

export default [
  { ignores: ['**/node_modules/**', ...ignorar] },
  {
    files: ['**/*.js', '**/*.cjs'],
    languageOptions: { ecmaVersion: 'latest', sourceType: 'commonjs', globals: globals.node },
    linterOptions: opcoes,
    rules: { ...correcao, ...saude },
  },
  {
    files: ['**/*.mjs'],
    languageOptions: { ecmaVersion: 'latest', sourceType: 'module', globals: globals.node },
    linterOptions: opcoes,
    rules: { ...correcao, ...saude },
  },
  {
    files: ['**/*.ts', '**/*.mts', '**/*.cts'],
    languageOptions: { parser: tsParser, ecmaVersion: 'latest', sourceType: 'module', globals: globals.node },
    linterOptions: opcoes,
    rules: { ...correcao, ...saude },
  },
  {
    files: ['.pi/extensions/**/*.ts', '.pi/extensions/**/*.mts'],
    rules: extensoesDoPi,
  },
];
