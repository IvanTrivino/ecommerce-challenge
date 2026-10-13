import { Column, Hr, Row, Section, Text } from "@react-email/components"
import { LinkButton } from "../ui/Button"
import { Heading } from "../ui/Heading"
import { Layout } from "../ui/Layout"

type OrderPlacedProps = {
  project_name: string
  number: string
  placed_at: string
  total_price: string
  total_weight: string
  payment_reference: string
  link: string
}

export default function OrderPlaced({
  project_name = "{{ project_name }}",
  number = "{{ number }}",
  placed_at = "{{ placed_at }}",
  total_price = "{{ total_price }}",
  total_weight = "{{ total_weight }}",
  payment_reference = "{{ payment_reference }}",
  link = "{{ link }}",
}: OrderPlacedProps) {
  return (
    <Layout
      title={`${project_name} - Order confirmed`}
      preview={`Order #${number} confirmed`}
      project_name={project_name}
    >
      <Heading>Thanks for your order</Heading>
      <Text style={bodyTextStyle}>
        Order #{number} · {placed_at}
      </Text>
      <Row>
        <Column style={{ ...headerCell, width: "48%" }}>Item</Column>
        <Column style={{ ...headerCell, width: "12%" }}>Qty</Column>
        <Column style={{ ...headerCell, ...rightCell, width: "20%" }}>
          Price
        </Column>
        <Column style={{ ...headerCell, ...rightCell, width: "20%" }}>
          Total
        </Column>
      </Row>
      <Section>
        {"{% for item in items %}"}
        <Row>
          <Column style={{ ...itemCell, width: "48%" }}>
            {"{{ item.name }}"}
            <br />
            <span style={skuStyle}>{"{{ item.sku }}"}</span>
          </Column>
          <Column style={{ ...itemCell, width: "12%" }}>
            ×{"{{ item.quantity }}"}
          </Column>
          <Column style={{ ...itemCell, ...rightCell, width: "20%" }}>
            {"{{ item.unit_price }}"}
          </Column>
          <Column style={{ ...itemCell, ...rightCell, width: "20%" }}>
            {"{{ item.line_total }}"}
          </Column>
        </Row>
        {"{% endfor %}"}
      </Section>
      <Hr style={ruleStyle} />
      <Text style={totalsStyle}>Total weight: {total_weight}</Text>
      <Text style={{ ...totalsStyle, fontSize: "17px", fontWeight: "700" }}>
        Total: {total_price}
      </Text>
      <Text style={supportingTextStyle}>
        Payment reference {payment_reference}
      </Text>
      <LinkButton href={link}>View your order</LinkButton>
    </Layout>
  )
}

const bodyTextStyle = {
  color: "#334155",
  fontSize: "15px",
  lineHeight: "26px",
  margin: "0 0 18px",
}

const supportingTextStyle = {
  color: "#64748b",
  fontSize: "14px",
  lineHeight: "23px",
  margin: "0 0 16px",
}

const headerCell = {
  borderBottom: "1px solid #e0e2f3",
  color: "#64748b",
  fontSize: "11px",
  fontWeight: "700",
  letterSpacing: "1px",
  padding: "0 0 8px",
  textTransform: "uppercase" as const,
  verticalAlign: "top" as const,
}

const itemCell = {
  borderBottom: "1px solid #e9ebfa",
  color: "#1e293b",
  fontSize: "14px",
  lineHeight: "22px",
  padding: "10px 0",
  verticalAlign: "top" as const,
}

const rightCell = {
  textAlign: "right" as const,
}

const skuStyle = {
  color: "#64748b",
  fontFamily: 'Consolas, "Courier New", monospace',
  fontSize: "12px",
}

const ruleStyle = {
  border: "0",
  borderTop: "1px solid #e0e2f3",
  margin: "8px 0 16px",
}

const totalsStyle = {
  color: "#1e293b",
  fontSize: "14px",
  lineHeight: "22px",
  margin: "0 0 6px",
  textAlign: "right" as const,
}
