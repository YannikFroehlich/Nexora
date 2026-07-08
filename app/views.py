from django.shortcuts import render

# Create your views here.

def home(request):
    template_name = 'app/home.html'
    return render(request, template_name)

def about(request):
    template_name = 'app/about.html'
    return render(request, template_name)