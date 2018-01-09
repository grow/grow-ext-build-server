var buildServer = buildServer || {};


buildServer.main = function() {
  var app = angular.module('buildServer', []);
  app.config(function($interpolateProvider) {
    $interpolateProvider.startSymbol('[[').endSymbol(']]');
  });
  app.controller('ManageUsersController', buildServer.ng.ManageUsersController);
  app.controller('ManageUserController', buildServer.ng.ManageUserController);
  app.controller('BuildStatusController', buildServer.ng.BuildStatusController);
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


buildServer.ng.ManageUserController = function($scope, $element) {
  this.$scope = $scope;
  this.el = $element[0];
  this.user = {};
  this.email = null;
};


buildServer.ng.ManageUserController.prototype.addToAllUnlocked =
    function() {
  [].forEach.call(this.user['folders'], function(folder) {
    if (folder['title'].indexOf('Archive') >= 1) {
      return;
    }
    folder['has_access'] = true;
  }.bind(this));
  this.serializeAndUpdateFolders();
};


buildServer.ng.ManageUserController.prototype.serializeAndUpdateFolders =
    function() {
  var user = {
    'email': this.email,
    'folders': this.user.folders
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


buildServer.ng.ManageUserController.prototype.sendEmailNotification = function(user) {
  buildServer.rpc('users.send_email_notification', {
    'user': {'email': this.email}
  }).then(function(resp) {
    alert('An email was sent.');
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
  this.foldersToImport = {};
  this.user = {};
  this.search();
};


buildServer.ng.ManageUsersController.prototype.search =
    function(query, opt_nextCursor) {
  this.isLoadingUsers = true;
  buildServer.rpc('users.search', {
    'query': query
  }).then(function(resp) {
    this.isLoadingUsers = false;
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


buildServer.ng.ManageUsersController.prototype.importFromSheets = function(sheetId, sheetGid) {
  var folders = [];
  this.isWorking = true;
  for (var folderId in this.foldersToImport) {
    folders.push({
      'folder_id': folderId,
      'has_access': true
    });
  }
  buildServer.rpc('users.import_from_sheets', {
    'sheet_id': sheetId,
    'folders': folders,
    'sheet_gid': sheetGid,
  }).then(function(resp) {
    console.log(resp);
    this.isWorking = false;
    this.numImported = resp['num_imported'];
    this.$scope.$apply();
    this.search();
  }.bind(this), function() {
    this.isWorking = false;
    this.importError = true;
    this.$scope.$apply();
  }.bind(this));
};


buildServer.ng.BuildStatusController = function() {
};


buildServer.ng.BuildStatusController.prototype.rebuild = function(url) {
  var resp = $.ajax({
      url: url,
      type: 'POST'
  });
  this.isRebuildRequested = true;
};
