var buildServer = buildServer || {};


buildServer.main = function() {
  var app = angular.module('buildServer', []);
  app.config(function($interpolateProvider) {
    $interpolateProvider.startSymbol('[[').endSymbol(']]');
  });
  app.controller('ManageUsersController', buildServer.ng.ManageUsersController);
  app.controller('ManageUserController', buildServer.ng.ManageUserController);
  angular.bootstrap(document, ['buildServer']);
};


buildServer.rpc = function(method, data) {
  return $.ajax({
      url: '/_grow/api/' + method,
      type: 'POST',
      data: JSON.stringify(data),
      contentType: 'application/json'
  });
};


buildServer.ng = buildServer.ng || {};


buildServer.ng.ManageUserController = function($scope) {
  this.$scope = $scope;
  this.user = {};
  this.email = null;
};


buildServer.ng.ManageUserController.prototype.setEmail = function(email) {
  this.email = email;
  this.update();
};


buildServer.ng.ManageUserController.prototype.update = function() {
  buildServer.rpc('users.get', {
    'user': {'email': this.email}
  }).then(function(resp) {
    this.user = resp['user'];
    this.$scope.$apply();
  }.bind(this));
};


buildServer.ng.ManageUsersController = function($scope) {
  this.$scope = $scope;
  this.user = {};
  this.update();
};


buildServer.ng.ManageUsersController.prototype.update =
    function(opt_nextCursor) {
  buildServer.rpc('users.search', {}).then(function(resp) {
    this.users = resp['users'];
    this.$scope.$apply();
  }.bind(this));
};


buildServer.ng.ManageUsersController.prototype.create = function(email) {
  buildServer.rpc('users.create', {
    'user': {
      'email': email
    }
  }).then(function(resp) {
    // Remove existing user from the list.
    this.users = this.users.filter(function(user) {
      return user['email'] != resp['user']['email'];
    });
    // Add new user to front of list.
    this.users.unshift(resp['user']);
    this.$scope.$apply();
  }.bind(this));
};
