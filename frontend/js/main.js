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
  this.folders = {};

  this.user = {};
  this.email = null;
};


buildServer.ng.ManageUserController.prototype.serializeAndUpdateFolders =
    function() {
  var folders = [];
  for (var key in this.folders) {
    if (this.folders[key]) {
      folders.push({
        'folder_id': key,
        'has_access': true
      });
    }
  }
  var user = {
    'email': this.email,
    'folders': folders
  };
  this.update(user);
};


buildServer.ng.ManageUserController.prototype.setEmail = function(email) {
  this.email = email;
  this.get();
};


buildServer.ng.ManageUserController.prototype.deleteUser = function() {
  buildServer.rpc('users.delete', {
    'user': {'email': this.email}
  }).then(function(resp) {
    window.setTimeout(function() {
      window.location = '/_grow/users';
    });
    this.$scope.$apply();
  }.bind(this));
};


buildServer.ng.ManageUserController.prototype.update = function(user) {
  buildServer.rpc('users.update', {
    'user': user 
  }).then(function(resp) {
    this.setUserResponse(resp['user']);
  }.bind(this));
};


buildServer.ng.ManageUserController.prototype.setUserResponse =
    function(user) {
  this.user = user;
  for (var i in this.user.folders) {
    var folder = this.user.folders[i];
    if (folder['has_access']) {
      this.folders[folder['folder_id']] = true;
    }
  }
  this.$scope.$apply();
};


buildServer.ng.ManageUserController.prototype.get = function() {
  buildServer.rpc('users.get', {
    'user': {'email': this.email}
  }).then(function(resp) {
    this.setUserResponse(resp['user']);
  }.bind(this));
};


buildServer.ng.ManageUsersController = function($scope) {
  this.$scope = $scope;
  this.user = {};
  this.search();
};


buildServer.ng.ManageUsersController.prototype.search =
    function(query, opt_nextCursor) {
  buildServer.rpc('users.search', {
    'query': query
  }).then(function(resp) {
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
    if (!this.users) {
      this.users = [];
    }
    this.users = this.users.filter(function(user) {
      return user['email'] != resp['user']['email'];
    });
    // Add new user to front of list.
    this.users.unshift(resp['user']);
    this.$scope.$apply();
  }.bind(this));
};
