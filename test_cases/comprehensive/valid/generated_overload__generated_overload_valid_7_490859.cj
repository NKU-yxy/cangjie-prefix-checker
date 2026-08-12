main(): Unit {
    let values_7_490859: ArrayList<Int64> = ArrayList<Int64>(20)
    values_7_490859.add(1)
    values_7_490859.add(ArrayList<Int64>())
    values_7_490859.add(61, 0)

    let clone_7_490859: () -> ArrayList<Int64> = values_7_490859.clone
    let copied_7_490859: ArrayList<Int64> = clone_7_490859()
}
