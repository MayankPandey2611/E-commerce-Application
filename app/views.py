# shop/views.py
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from .models import Category, Product, Order, OrderItem

# ---------- Helpers: session cart ----------
def _get_cart(request):
    cart = request.session.get('cart', {})  # {product_id: qty}
    return cart

def _save_cart(request, cart):
    request.session['cart'] = cart
    request.session.modified = True

# ---------- Product List / Detail ----------
def product_list(request, slug=None):
    categories = Category.objects.all().order_by('name')
    products = Product.objects.filter(is_active=True)

    # category filter
    current_category = None
    if slug:
        current_category = get_object_or_404(Category, slug=slug)
        products = products.filter(category=current_category)

    # search
    q = request.GET.get('q')
    if q:
        products = products.filter(
            Q(name__icontains=q) | Q(description__icontains=q)
        )

    # sort (optional)
    sort = request.GET.get('sort')  # 'price_asc' | 'price_desc' | 'new'
    if sort == 'price_asc':
        products = products.order_by('price')
    elif sort == 'price_desc':
        products = products.order_by('-price')
    elif sort == 'new':
        products = products.order_by('-created_at')

    return render(request, 'shop/product_list.html', {
        'categories': categories,
        'products': products,
        'current_category': current_category,
        'q': q or '',
        'sort': sort or '',
        'cart_count': sum(_get_cart(request).values()),
    })


def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    return render(request, 'shop/product_detail.html', {
        'product': product,
        'cart_count': sum(_get_cart(request).values()),
    })

# ---------- Cart ----------
def cart_view(request):
    cart = _get_cart(request)
    items = []
    total = 0
    for pid, qty in cart.items():
        product = get_object_or_404(Product, pk=pid, is_active=True)
        qty = int(qty)
        subtotal = product.price * qty
        total += subtotal
        items.append({'product': product, 'qty': qty, 'subtotal': subtotal})
    return render(request, 'shop/cart.html', {
        'items': items,
        'total': total,
        'cart_count': sum(cart.values()),
    })


def cart_add(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    cart = _get_cart(request)
    cart[str(product_id)] = cart.get(str(product_id), 0) + 1
    _save_cart(request, cart)
    messages.success(request, f"Added {product.name} to cart.")
    return redirect('cart')


def cart_update(request, product_id):
    if request.method == 'POST':
        qty = int(request.POST.get('qty', '1'))
        cart = _get_cart(request)
        if qty <= 0:
            cart.pop(str(product_id), None)
        else:
            cart[str(product_id)] = qty
        _save_cart(request, cart)
    return redirect('cart')


def cart_remove(request, product_id):
    cart = _get_cart(request)
    cart.pop(str(product_id), None)
    _save_cart(request, cart)
    return redirect('cart')


# ---------- Checkout / Order ----------
@login_required
def checkout(request):
    cart = _get_cart(request)
    if not cart:
        messages.error(request, "Your cart is empty.")
        return redirect('product_list')

    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        address = request.POST.get('address')
        city = request.POST.get('city')
        state = request.POST.get('state')
        pincode = request.POST.get('pincode')

        order = Order.objects.create(
            user=request.user,
            full_name=full_name,
            email=email,
            phone=phone,
            address=address,
            city=city,
            state=state,
            pincode=pincode,
            paid=True,  # simulate success
        )

        # create order items
        for pid, qty in cart.items():
            product = get_object_or_404(Product, pk=pid, is_active=True)
            qty = int(qty)
            OrderItem.objects.create(
                order=order,
                product=product,
                qty=qty,
                price=product.price,
            )
            # optional: reduce stock
            product.stock = max(0, product.stock - qty)
            product.save()

        # clear cart
        _save_cart(request, {})

        return redirect('order_success', order_id=order.id)

    # prefill form with user
    return render(request, 'shop/checkout.html', {
        'user': request.user,
        'cart_count': sum(cart.values()),
    })


@login_required
def order_success(request, order_id):
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    return render(request, 'shop/order_success.html', {'order': order})


# ---------- Auth (simple) ----------
def login_view(request):
    if request.user.is_authenticated:
        return redirect('product_list')
    error = None
    if request.method == 'POST':
        email_or_username = request.POST.get('username')
        password = request.POST.get('password')
        # Allow login via username or email
        user = authenticate(request, username=email_or_username, password=password)
        if not user:
            # try email→username
            try:
                u = User.objects.get(email=email_or_username)
                user = authenticate(request, username=u.username, password=password)
            except User.DoesNotExist:
                pass
        if user:
            login(request, user)
            return redirect('product_list')
        error = "Invalid credentials"
    return render(request, 'shop/auth_login.html', {'error': error})


def register_view(request):
    if request.user.is_authenticated:
        return redirect('product_list')
    error = None
    if request.method == 'POST':
        username = request.POST.get('username').strip()
        email = request.POST.get('email').strip().lower()
        password = request.POST.get('password')
        cp = request.POST.get('confirm_password')
        if password != cp:
            error = "Passwords do not match"
        elif User.objects.filter(username=username).exists():
            error = "Username already taken"
        elif User.objects.filter(email=email).exists():
            error = "Email already registered"
        else:
            User.objects.create_user(username=username, email=email, password=password)
            messages.success(request, "Registration successful. Please log in.")
            return redirect('login')
    return render(request, 'shop/auth_register.html', {'error': error})


def logout_view(request):
    logout(request)
    return redirect('product_list')
