#include <bits/stdc++.h>
using namespace std;

int main()
{
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int sum = 0;
    int co = 0;
    for (int i = 0; i < INT_MAX; i++)
    {
        string module;
        int data;
        cin >> module >> data;
        if(data > 0)
        {
            sum += data;
            co++;
        }
        if (data == 0 && sum != 0)
        {
            cout << module << " " << sum/co << endl;
            co = 0;
            sum = 0;
        }
    }
    return 0;
}