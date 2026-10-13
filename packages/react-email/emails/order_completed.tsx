import { OrderNotice } from "../ui/OrderNotice"

type OrderCompletedProps = {
  project_name: string
  number: string
  total_price: string
  link: string
}

export default function OrderCompleted({
  project_name = "{{ project_name }}",
  number = "{{ number }}",
  total_price = "{{ total_price }}",
  link = "{{ link }}",
}: OrderCompletedProps) {
  return (
    <OrderNotice
      project_name={project_name}
      title="Order completed"
      heading="Your order is complete"
      number={number}
      message={`(${total_price}) is complete.`}
      link={link}
    />
  )
}
