export const mockRestaurants = [
  {
    id: "1",
    name: "Ресторан 1",
    description:
      "Изысканная кухня в центре города. Здесь вы сможете насладиться блюдами от шеф-повара мирового уровня.",
    fullDescription:
      "Изысканная кухня в центре города. Здесь вы сможете насладиться блюдами от шеф-повара мирового уровня. Ресторан предлагает уникальную атмосферу, сочетающую традиции и современность. Наша кухня вдохновлена классическими рецептами с современным твистом. Мы используем только свежие ингредиенты от местных фермеров. Добро пожаловать в мир вкусов и ароматов, где каждый ужин становится событием.",
    address: "Москва, ул. Ленина, 1",
    hours: "23:00",
    avgCheck: "1500₽",
    image: "/images/photo.jpg",
    gallery: [
      {
        url: "/images/photo.jpg",
        type: "interior",
      },
      { url: "/images/photo.jpg", type: "dishes" },
      {
        url: "/images/photo.jpg",
        type: "interior",
      },
      { url: "/images/photo.jpg", type: "dishes" },
      { url: "/images/photo.jpg", type: "all" },
    ],
    menuItems: [
      { name: "Caesar Salad", price: 450, image: "/images/photo.jpg" },
      { name: "Margherita Pizza", price: 600, image: "/images/photo.jpg" },
      { name: "Grilled Salmon", price: 800, image: "/images/photo.jpg" },
      // ... more menu items
    ],
    menuPdf: "https://example.com/menu.pdf", // Placeholder PDF
    schedule: {
      monday: "09:00 - 22:00",
      tuesday: "09:00 - 22:00",
      wednesday: "09:00 - 22:00",
      thursday: "09:00 - 22:00",
      friday: "09:00 - 01:00",
      saturday: "10:00 - 01:00",
      sunday: "10:00 - 22:00",
    },
    kitchen: "Европейская, Азиатская",
    features: "Живая музыка, Винная карта, Терраса",
    chef: {
      name: "Шеф-повар Иван Иванов",
      description:
        "Опытный шеф с 20-летним стажем. Специализируется на фьюжн-кухне. Работал в Michelin-звездных ресторанах Европы. Его блюда сочетают традиции и инновации.",
      photo: "/images/20160314-WED_2158.jpg",
    },
    events: [
      {
        image: "/images/photo.jpg",
        name: "Винная дегустация",
        cost: "Бесплатно",
        address: "ул. Ленина, 1",
        restaurantName: "Ресторан 1",
      },
      {
        image: "/images/photo.jpg",
        name: "Живая музыка",
        cost: "500₽",
        address: "ул. Ленина, 1",
        restaurantName: "Ресторан 1",
      },
    ],
    location: { lat: 55.7558, lng: 37.6173, address: "Москва, ул. Ленина, 1" },
  },
  {
    id: "2",
    name: "Ресторан 2",
    description: "Уютное место для семейных ужинов",
    address: "Москва, ул. Тверская, 10",
    hours: "22:00",
    avgCheck: "1200₽",
    image: "/images/photo.jpg",
  },
  {
    id: "3",
    name: "Ресторан 3",
    description: "Лучшие морепродукты в городе",
    address: "Москва, ул. Арбат, 5",
    hours: "00:00",
    avgCheck: "2000₽",
    image: "/images/photo.jpg",
  },
  {
    id: "4",
    name: "Ресторан 4",
    description: "Современная кухня и панорамный вид",
    address: "Москва, ул. Новый Арбат, 15",
    hours: "23:00",
    avgCheck: "1800₽",
    image: "/images/photo.jpg",
  },
  {
    id: "5",
    name: "Ресторан 5",
    description: "Традиционные блюда с новым вкусом",
    address: "Москва, ул. Пятницкая, 20",
    hours: "22:30",
    avgCheck: "1400₽",
    image: "/images/photo.jpg",
  },
  {
    id: "6",
    name: "Ресторан 6",
    description: "Атмосферное место для встреч",
    address: "Москва, ул. Большая Никитская, 12",
    hours: "23:00",
    avgCheck: "1600₽",
    image: "/images/photo.jpg",
  },
];
