export type UserContact = {
  firstName: string
  lastName: string
  email: string
  phone: string
}

export type Booking = {
  id: string
  hotelId: string
  roomId: string
  checkIn: string
  checkOut: string
  guests: number
  totalPrice: number
  status: 'confirmed' | 'pending' | 'cancelled'
  contact: UserContact
  createdAt: string
}

export type Trip = {
  bookingId: string
  hotelId: string
  roomId: string
  checkIn: string
  checkOut: string
  guests: number
  guestNames: string[]
  totalPrice: string
  paymentStatus: string
  cancellationDeadline: string
  checkInTime: string
  documentsReady: boolean
}
