
#from views.groups import Groups

classes = {
	# 'groups': Groups(), # create instance of Group view
}

def dispatcher(request):
	path = request.path_info.strip('/').split('/')
	
	handlerName = 'handler'
	if path[0].lower() == 'ajax':
		handlerName = 'ajax_handler'
		del path[0]
	
	if path[0].lower() in classes:
		cls = classes[path[0].lower()]
		if not hasattr(cls, handlerName):
			raise Exception, "No handler %r found for view %r" % (handlerName, path[0].lower())
		
		del path[0]
		handler = getattr(cls, handlerName)
		response = handler(request, path)
		
		if not issubclass(response.__class__, Response):
			raise Exception, "Handler %r should return a Response instance" % handler
		
		request.setHeaders(response.headers)
		request.writeHeaders()
		request.write(response.content)