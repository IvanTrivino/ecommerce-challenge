import { Text } from "@react-email/components"
import { LinkButton } from "./Button"
import { Heading } from "./Heading"
import { Layout } from "./Layout"

type OrderNoticeProps = {
  project_name: string
  title: string
  heading: string
  number: string
  message: string
  link: string
}

export const OrderNotice = ({
  project_name,
  title,
  heading,
  number,
  message,
  link,
}: OrderNoticeProps) => (
  <Layout
    title={`${project_name} - ${title}`}
    preview={`Order #${number} ${message}`}
    project_name={project_name}
  >
    <Heading>{heading}</Heading>
    <Text style={bodyTextStyle}>
      Order #{number} {message}
    </Text>
    <LinkButton href={link}>View your order</LinkButton>
  </Layout>
)

const bodyTextStyle = {
  color: "#334155",
  fontSize: "15px",
  lineHeight: "26px",
  margin: "0 0 18px",
}
