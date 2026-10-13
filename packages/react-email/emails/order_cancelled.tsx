import { OrderNotice } from "../ui/OrderNotice"

type OrderCancelledProps = {
  project_name: string
  number: string
  total_price: string
  link: string
}

export default function OrderCancelled({
  project_name = "{{ project_name }}",
  number = "{{ number }}",
  total_price = "{{ total_price }}",
  link = "{{ link }}",
}: OrderCancelledProps) {
  return (
    <OrderNotice
      project_name={project_name}
      title="Order cancelled"
      heading="Your order was cancelled"
      number={number}
      message={`(${total_price}) has been cancelled.`}
      link={link}
    />
  )
}
