// Karma configuration (Angular 21 keeps Karma as a supported runner; the CLI default content is reproduced here plus one framework).
// https://karma-runner.github.io/6.4/config/configuration-file.html
//
// bracket-safe-paths — why: Karma feeds every entry of `files` to glob 7 / minimatch after `path.normalize`, so on Windows any
// glob metacharacter in a path is fatal (backslashes cannot escape, and `[[]` / `?` variants were measured to match nothing).
// This repository lives under a folder named "[Pro]", and the framework plugins inject the ABSOLUTE paths of their adapters
// (karma-jasmine boot/adapter, jasmine-core, karma-source-map-support): none is found and the run dies with "describe is not
// defined". The framework below runs after those plugins and moves only the root Karma resolves: it creates a directory junction
// without brackets in the temp folder (no privileges needed on Windows) that points at this frontend folder and rewrites the
// injected patterns onto it, so glob takes its literal (non-magic) fast path. It is a no-op when the path has no brackets, so the
// same file serves a checkout at C:\fps_ng21 and one under "[Pro]". Documented in docs/architecture/frontend_architecture.md.

const fs = require('fs');
const os = require('os');
const path = require('path');

function bracketSafePaths(files, logger) {
  const log = logger.create('framework.bracket-safe-paths');
  const root = __dirname;
  if (!/[[\]]/.test(root)) {
    return;
  }
  const link = path.join(os.tmpdir(), 'fps-karma-root');
  let current = null;
  try {
    current = fs.readlinkSync(link);
  } catch (e) {
    current = null;
  }
  if (current !== root) {
    try {
      fs.rmSync(link, { force: true, recursive: false });
    } catch (e) {
      /* nothing to remove */
    }
    fs.symlinkSync(root, link, 'junction');
  }
  const rootLower = root.toLowerCase();
  const rewrite = (pattern) => {
    const normalized = path.normalize(pattern);
    return normalized.toLowerCase().startsWith(rootLower) ? link + normalized.slice(root.length) : pattern;
  };
  let moved = 0;
  for (let i = 0; i < files.length; i++) {
    const entry = files[i];
    if (typeof entry === 'string') {
      const next = rewrite(entry);
      moved += next !== entry;
      files[i] = next;
    } else if (entry && typeof entry.pattern === 'string') {
      const next = rewrite(entry.pattern);
      moved += next !== entry.pattern;
      entry.pattern = next;
    }
  }
  log.info(`workspace path contains brackets: ${moved} file pattern(s) resolved through ${link}`);
}
bracketSafePaths.$inject = ['config.files', 'logger'];

module.exports = function (config) {
  config.set({
    basePath: '',
    frameworks: ['jasmine', '@angular-devkit/build-angular', 'bracket-safe-paths'],
    plugins: [
      require('karma-jasmine'),
      require('karma-chrome-launcher'),
      require('karma-coverage'),
      require('@angular-devkit/build-angular/plugins/karma'),
      { 'framework:bracket-safe-paths': ['factory', bracketSafePaths] },
    ],
    client: {
      jasmine: {},
    },
    coverageReporter: {
      dir: path.join(__dirname, './coverage/frontend'),
      subdir: '.',
      reporters: [{ type: 'html' }, { type: 'text-summary' }],
    },
    reporters: ['progress'], // no kjhtml: the HTML reporter injects its own (bracketed) patterns after the frameworks and is useless headless
    browsers: ['ChromeHeadless'],
    restartOnFileChange: false, // never leave a watcher behind: a runaway watcher once grew to 16 GB of RAM
  });
};
