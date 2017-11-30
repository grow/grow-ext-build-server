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


buildServer.ng.ManageUserController = function($scope, $element) {
  this.$scope = $scope;
  this.folders = {};
  this.el = $element[0];

  this.user = {};
  this.email = null;
};


buildServer.ng.ManageUserController.prototype.addToAllUnlocked =
    function() {
  var folderInputEls = this.el.querySelectorAll('[data-folder-id]');
  [].forEach.call(folderInputEls, function(el) {
    var folderId = el.getAttribute('data-folder-id');
    var isLocked = el.getAttribute('data-locked');
    if (isLocked) {
      return;
    }
    this.folders[folderId] = true; 
  }.bind(this));
  this.serializeAndUpdateFolders();
};


buildServer.ng.ManageUserController.prototype.isFolderRequested =
    function(folderId) {
  var folder = this.user.folders;
  var isRequested = false;
  if (!this.user || !this.user.folders || !this.user.folders.length) {
    return false;
  }
  this.user.folders.forEach(function(folder) {
    if (folderId == folder['folder_id'] && folder['has_requested']) {
      isRequested = true;
    }
  });
  return isRequested;
};


buildServer.ng.ManageUserController.prototype.serializeAndUpdateFolders =
    function() {
  var folders = [];
  console.log(this.folders);
  var allFolderIds = [];
  var allFolderEls = document.querySelectorAll('[data-folder-id]');
  [].forEach.call(allFolderEls, function(folderEl) {
    allFolderIds.push(folderEl.getAttribute('data-folder-id'));
  });
  [].forEach.call(allFolderIds, function(folderId) {
    var hasAccess = this.folders[folderId];
    if (hasAccess) {
      var hasRequested = false;
    } else {
      var hasRequested = this.isFolderRequested(folderId);
    }
    folders.push({
      'folder_id': folderId,
      'has_requested': hasRequested,
      'has_access': hasAccess
    });
  }.bind(this));
  console.log(folders);
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


buildServer.ng.ManageUsersController.prototype.importFromSheets = function(sheetId, sheetGid) {
  buildServer.rpc('users.import_from_sheets', {
    'sheet_id': sheetId,
    'sheet_gid': sheetGid,
  }).then(function(resp) {
    console.log(resp);
    this.$scope.$apply();
  }.bind(this));
};
