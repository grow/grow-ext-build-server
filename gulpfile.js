var autoprefixer = require('gulp-autoprefixer');
var gulp = require('gulp');
var concat = require('gulp-concat');
var plumber = require('gulp-plumber');
var runSequence = require('run-sequence');
var sass = require('gulp-sass');
var uglify = require('gulp-uglify');

var Path = {
  CSS_SOURCES: [
    './frontend/sass/**'
  ],
  CSS_OUT_DIR: './dist/css/',
  JS_SOURCES: './frontend/js/*.js',
  JS_OUT_DIR: './dist/js/',
};

var onError = function() {
  var args = Array.prototype.slice.call(arguments);
  console.log(args);
  this.emit('end');
};

gulp.task('buildcss', function(callback) {
  return runSequence(
      'sass',
      callback
  );
});

gulp.task('sass', function() {
  return gulp.src('./frontend/sass/*')
    .pipe(plumber())
    .pipe(sass({
        outputStyle: 'compressed'
    }))
    .on('error', onError)
    .pipe(autoprefixer({
        'browsers': [
            '> 1%',
            'last 2 versions',
            'Firefox ESR',
            'Opera 12.1',
            'iOS 7'
        ]
    }))
    .pipe(gulp.dest(Path.CSS_OUT_DIR));
});

gulp.task('minifyjs', function() {
  return gulp.src([
      './node_modules/smooth-scroll/dist/js/smooth-scroll.js',
      Path.JS_SOURCES,
  ])
    .pipe(uglify({
      mangle: false,
      compress: true,
    }))
    .pipe(concat('main.min.js'))
    .pipe(gulp.dest(Path.JS_OUT_DIR));
});

gulp.task('watch', function() {
  gulp.watch(Path.CSS_SOURCES, ['buildcss']);
  gulp.watch(Path.JS_SOURCES, ['minifyjs']);
});

gulp.task('build', ['buildcss', 'minifyjs']);
gulp.task('default', ['build', 'watch']);
