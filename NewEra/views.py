
# IMPORTS 

import ast
import os
from datetime import datetime

from django.http import Http404, HttpResponse, HttpResponseRedirect #, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie

from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login # 'login' can't clash w/view names in namespace 
from django.contrib.auth import logout as auth_logout # 'logout' can't clash w/view names in namespace 
from django.contrib import messages

from django.utils import timezone

from NewEra.models import User, CaseLoadUser, Resource, Referral, Tag, SMS_CARRIERS
from NewEra.forms import LoginForm, RegistrationForm, EditUserForm, EditSelfUserForm, CaseLoadUserForm, CreateResourceForm, TagForm, ResourceFilter

# VIEW ACTIONS 

def home(request): 
	markReferralAsSeen(request)
	return render(request, 'NewEra/index.html', {})

def resources(request):
	all_resources = Resource.objects.all()

	context = {
		'resources': all_resources,
		'active_resources': all_resources.filter(is_active=True),
		'inactive_resources': all_resources.filter(is_active=False),
		'tags': Tag.objects.all()
	}

	context['filter'] = ResourceFilter(request.GET, queryset=context['resources'])

	if request.method == 'GET':
		context['active_resources'] = context['filter'].qs.filter(is_active=True)
		context['inactive_resources'] = context['filter'].qs.filter(is_active=False)

	return render(request, 'NewEra/resources.html', context)

def get_resource(request, id):
	resource = get_object_or_404(Resource, id=id)
	context = { 'resource': resource, 'tags': resource.tags.all() }
	response = render(request, 'NewEra/get_resource.html', context)
	
	# Update clicks
	if isUniqueVisit(request, response, id):
		resource.clicks = resource.clicks + 1
		resource.save()

	markReferralAsSeen(request)

	return response

# Function to check visitor cookie, and see if they accessed the resource
def isUniqueVisit(request, response, id): 
	siteStaff = request.COOKIES.get('siteStaff', '')

	if request.user.is_authenticated or siteStaff == 'true':
		response.set_cookie('siteStaff', 'true')
		return False 

	visitedResources = request.COOKIES.get('visitedResources', '').split(';')

	if visitedResources == ['']:
		response.set_cookie('visitedResources', str(id))
		return True 
	elif str(id) in visitedResources:
		return False
	else: 
		val = ';'.join(visitedResources)
		val = val + ';' + str(id)
		response.set_cookie('visitedResources', val)
		return True 
	
	return False 

	

# Function to update the referral given a GET request with a querystring timestamp
def markReferralAsSeen(request):
	if 'key' not in request.GET:
		return 

	keyDate = datetime.strptime(request.GET['key'], '%Y-%m-%d %H:%M:%S.%f')
	referrals = Referral.objects.filter(referral_date=keyDate)
	
	if referrals.count() == 1:
		referral = referrals.first()
		referral.date_accessed = datetime.now()
		referral.save()

# ***** Note about images *****
# They are uploaded to the system as type .JPEG or .PNG etc.
# And then saved as type django.FileField() 
# *****************************
def get_resource_image(request, id): 
	resource = get_object_or_404(Resource, id=id)

	if not resource.image:
		raise Http404

	return HttpResponse(resource.image, content_type=resource.content_type)

def login(request):
	if request.user.is_authenticated:
		return redirect(reverse('Home'))

	context = {
		'resources': Resource.objects.all(),
		'active_resources': Resource.objects.all().filter(is_active=True),
		'inactive_resources': Resource.objects.all().filter(is_active=False)
	}
	if request.method == 'GET':
		context['form'] = LoginForm()
		return render(request, 'NewEra/login.html', context)

	form = LoginForm(request.POST)
	context['form'] = form

	if not form.is_valid():
		return render(request, 'NewEra/login.html', context)

	user = authenticate(username=form.cleaned_data['username'],
							password=form.cleaned_data['password'])

	auth_login(request, user)
	return redirect(reverse('Home'))

@login_required
def logout(request):
	auth_logout(request)
	return redirect(reverse('Login'))

def about(request):
	return render(request, 'NewEra/about.html')

def create_resource(request):
	context = {}
	form = CreateResourceForm()
	context['form'] = form

	if request.method == 'POST':
		resource = Resource()
		form = CreateResourceForm(request.POST, request.FILES, instance=resource)
		
		if form.is_valid():
			# Update content_type
			pic = form.cleaned_data['image']
			if pic and pic != '':
				resource.content_type = form.cleaned_data['image'].content_type

				# REMOVE OLD IMAGE (for edit action)
				# if oldImageName: 
				# 	BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
				# 	IMAGE_ROOT = os.path.join(BASE_DIR, 'socialnetwork/user_uploads/' + oldImageName.name)
				# 	os.remove(IMAGE_ROOT)

			form.save()
			resource.save()

			messages.success(request, 'Form submission successful')

			return redirect('Resources')
	else:
		form = CreateResourceForm()

	return render(request, 'NewEra/edit_resource.html', context)

# SOW Actions 

def create_referral(request):
	resources = request.GET.get('resources', None)	

	if request.method == 'GET' and resources:
		resources = [digit.strip() for digit in ast.literal_eval(resources)] # Safely parse array
		resources = [ get_object_or_404(Resource, id=resourceId) for resourceId in resources ]

		recipients = [] 
		carriers = list(SMS_CARRIERS.keys())
		if request.user.is_superuser: 
			recipients = CaseLoadUser.objects.all()
		elif request.user.is_staff: 
			recipients = recipients = CaseLoadUser.objects.filter(user=request.user)

		return render(request, 'NewEra/create_referral.html', {'resources': resources, 'recipients': recipients, 'carriers': carriers})

	elif request.method == 'POST': 
		phoneInput = ''.join(digit for digit in request.POST.get('phone', '') if digit.isdigit())
		
		if 'resources[]' in request.POST and 'user_id' in request.POST and 'carrier' in request.POST and 'notes' in request.POST: 
			caseload_user = get_object_or_404(CaseLoadUser, id=request.POST['user_id'])
			resources = [get_object_or_404(Resource, id=num) for num in request.POST.getlist('resources[]')]
			referral = Referral(email='', phone='', notes=request.POST['notes'], user=request.user, caseUser=caseload_user)

		elif 'resources[]' in request.POST and 'phone' in request.POST and 'carrier' in request.POST and 'email' in request.POST and 'notes' in request.POST and len(phoneInput) == 10: 
			resources = [get_object_or_404(Resource, id=num) for num in request.POST.getlist('resources[]')]
			referral = Referral(email=request.POST['email'], phone=phoneInput, notes=request.POST['notes'], user=request.user)
			
		else: 
			# REQUIRES "MESSAGE" IN TEMPLATE 
			msg = 'Please fill out all fields.'
			return render(request, 'NewEra/create_referral.html', {'resources': resources, 'recipients': recipients, 'carriers': carriers, 'message': msg })
		
		referral.save()

		for r in resources: 
			referral.resource_set.add(r)

		carrierList = list(SMS_CARRIERS.keys())
		carrier = request.POST['carrier']

		if carrier not in carrierList: 
			raise Http404
		
		referralTimeStamp = str(referral.referral_date)
		referral.sendEmail(referralTimeStamp)
		referral.sendSMS(carrier, referralTimeStamp)

	return redirect(reverse('Resources'))

def referrals(request):
	if (request.user.is_superuser):
		referrals = Referral.objects.all()
	elif (request.user.is_staff):
		referrals = Referral.objects.all().filter(user=request.user)

	context = {
		'referrals': referrals
	}

	return render(request, 'NewEra/referrals.html', context)

def get_referral(request, id):
	referral = get_object_or_404(Referral, id=id)
	context = { 'referral': referral, 'resources': Resource.objects.all().filter(referrals=referral) }
	return render(request, 'NewEra/get_referral.html', context)

def case_load(request):
	users = [] 
	context = {} 

	if request.user.is_superuser: 
		users = CaseLoadUser.objects.all()	
		context['staff'] = User.objects.order_by('first_name', 'last_name')
	elif request.user.is_staff:
		users = CaseLoadUser.objects.filter(user=request.user).order_by('first_name', 'last_name')
	else:  
		raise Http404

	if request.method == 'POST' and 'staff_id' in request.POST:
		staff_user = get_object_or_404(User, id=request.POST['staff_id'])
		load_user = CaseLoadUser(user=staff_user)
		form = CaseLoadUserForm(request.POST, instance=load_user)

		if not form.is_valid():
			context['form'] = form 
			return render(request, 'NewEra/case_load.html', context)

		form.save()
		load_user.save() 

	context['caseload_users'] = users
	context['form'] = CaseLoadUserForm()
	return render(request, 'NewEra/case_load.html', context)

def get_case_load_user(request, id):
	case_load_user = get_object_or_404(CaseLoadUser, id=id)
	context = { 'case_load_user': case_load_user }
	return render(request, 'NewEra/get_case_load_user.html', context)

def edit_case_load_user(request, id):
	case_load_user = get_object_or_404(CaseLoadUser, id=id)

	if request.method == "POST":
		form = CaseLoadUserForm(request.POST, instance=case_load_user)
    
		if form.is_valid():

			form.save()
			case_load_user.save()

			return redirect('Show Case Load User', id=case_load_user.id)
	else:
		form = CaseLoadUserForm(instance=case_load_user)
	return render(request, 'NewEra/edit_case_load_user.html', {'form': form, 'case_load_user': case_load_user, 'action': 'Edit'})

def delete_case_load_user(request, id):
	case_load_user = get_object_or_404(CaseLoadUser, id=id)

	if request.method == 'POST':
		if (case_load_user.get_referrals().count() == 0):
			case_load_user.delete()
			messages.success(request, 'Case Load User successfully deleted.')
			return redirect('Case Load')
		else:
			case_load_user.is_active = False
			case_load_user.save()
			messages.success(request, 'case_load_user.get_full_name was made inactive.')
			return redirect('Show Case Load User', id=case_load_user.id)
	return render(request, 'NewEra/delete_case_load_user.html', {'case_load_user': case_load_user})


# ADMIN actions 

def manage_users(request): 
	if not request.user.is_superuser:
		raise Http404

	admins = User.objects.filter(is_superuser=True)
	sows = User.objects.filter(is_superuser=False).filter(is_staff=True)
	context = {'admins':admins, 'sows':sows, 'form': RegistrationForm()}

	if request.method == 'POST':
		form = RegistrationForm(request.POST)
		context['form'] = form

		if not form.is_valid():
			return render(request, 'NewEra/manage_users.html', context)

		user = User.objects.create_user(username=form.cleaned_data['username'], 
										password=form.cleaned_data['password'],
										email=form.cleaned_data['email'],
										phone=form.cleaned_data['phone'],
										first_name=form.cleaned_data['first_name'],
										last_name=form.cleaned_data['last_name'])
		user.is_staff = True 
		user.is_superuser = False

		# Radio button input 
		if 'user_type' in request.POST and request.POST['user_type'] == 'admin': 
			user.is_superuser = True

		user.save()
	
	context['form'] = RegistrationForm()
	return render(request, 'NewEra/manage_users.html', context)

def edit_user(request, id):
	user = get_object_or_404(User, id=id)

	if request.method == "POST":
		if user == request.user:
			form = EditSelfUserForm(request.POST, instance=user)
		else:
			form = EditUserForm(request.POST, instance=user)
    
		if form.is_valid():

			form.save()
			user.save()

			return redirect('Manage Users')
	else:
		if user == request.user:
			form = EditSelfUserForm(instance=user)
		else:
			form = EditUserForm(instance=user)
	return render(request, 'NewEra/edit_user.html', {'form': form, 'user': user, 'action': 'Edit'})

def delete_user(request, id):
	user = get_object_or_404(User, id=id)

	if request.method == 'POST':
		if (user.get_referrals().count() == 0 and user.get_case_load().count() == 0):
			user.delete()
			messages.success(request, 'User successfully deleted.')
			return redirect('Manage Users')
		else:
			user.is_active = False
			user.save()
			messages.success(request, 'user.get_full_name was made inactive.')
			return redirect('Manage Users')
	return render(request, 'NewEra/delete_user.html', {'user': user})

def create_resource(request):
	context = {}
	form = CreateResourceForm()
	context['form'] = form
	context['action'] = 'Create'

	if request.method == 'POST':
		resource = Resource()
		form = CreateResourceForm(request.POST, request.FILES, instance=resource)
		
		if form.is_valid():
			# Update content_type
			pic = form.cleaned_data['image']
			if pic and pic != '':
				print('Uploaded image: {} (type={})'.format(pic, type(pic)))
				resource.content_type = form.cleaned_data['image'].content_type

			form.save()
			resource.save()

			messages.success(request, 'Resource successfully created!')

			return redirect('Resources')
	else:
		form = CreateResourceForm()

	return render(request, 'NewEra/edit_resource.html', context)

def edit_resource(request, id):
	resource = get_object_or_404(Resource, id=id)
	oldImage = resource.image

	if request.method == "POST":
		form = CreateResourceForm(request.POST, request.FILES, instance=resource)
    
		if form.is_valid():

			pic = form.cleaned_data['image']
			if pic and pic != '':
				
				# Update content type, remove old image
				try: 
					# Edge case where revalidated file is a FieldFile type (and not an Image)
					resource.content_type = form.cleaned_data['image'].content_type
					deleteImage(oldImage)
				except: 
					pass

			form.save()
			resource.save()

			return redirect('Show Resource', id=resource.id)
	else:
		form = CreateResourceForm(instance=resource)
	return render(request, 'NewEra/edit_resource.html', {'form': form, 'resource': resource, 'action': 'Edit'})

def delete_resource(request, id):
	resource = get_object_or_404(Resource, id=id)

	if request.method == 'POST':
		if (resource.referrals.count() == 0):
			deleteImage(resource.image)
			resource.delete()
			messages.success(request, 'Resource successfully deleted.')
			return redirect('Resources')
		else:
			resource.is_active = False
			resource.save()
			messages.success(request, 'Resource was made inactive.')
			return redirect('Show Resource', id=resource.id)
	return render(request, 'NewEra/delete_resource.html', {'resource': resource})

# Deletes the given image if it exists
def deleteImage(oldImage):
	if oldImage: 
		BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
		IMAGE_ROOT = os.path.join(BASE_DIR, 'NewEra/user_uploads/' + oldImage.name)
		os.remove(IMAGE_ROOT)

# Creates tags
def tags(request):
	context = {
		'tags': Tag.objects.all()
	}
	return render(request, 'NewEra/tags.html', context)

def create_tag(request):
	context = {}
	form = TagForm()
	context['form'] = form
	context['action'] = 'Create'

	if request.method == 'POST':
		tag = Tag()
		form = TagForm(request.POST, instance=tag)
		
		if form.is_valid():
			form.save()
			tag.save()

			messages.success(request, 'Tag successfully created!')

			return redirect('Tags')
	else:
		tag = TagForm()

	return render(request, 'NewEra/edit_tag.html', context)

def edit_tag(request, id):
	tag = get_object_or_404(Tag, id=id)

	if request.method == "POST":
		form = TagForm(request.POST, instance=tag)
    
		if form.is_valid():
			form.save()
			tag.save()

			return redirect('Tags')
	else:
		form = TagForm(instance=tag)
	return render(request, 'NewEra/edit_tag.html', {'form': form, 'tag': tag, 'action': 'Edit'})

def delete_tag(request, id):
	tag = get_object_or_404(Tag, id=id)

	if request.method == 'POST':
		tag.delete()
		messages.success(request, 'Tag successfully deleted.')
		return redirect('Tags')

	return render(request, 'NewEra/delete_tag.html', {'tag': tag})
